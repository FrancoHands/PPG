from __future__ import annotations
import json
import re
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from clients.neo4j_client import resolve_items
from database import connect_db
from models import Action, Condition, EstadoEnum, Location, ObjectEntry, Procedure, State, Step, Task

# Cada categoría de "extras" se respalda en una label del catálogo Neo4j
CATALOG_LABEL_BY_KIND = {
    "acciones": "Accion",
    "objetos": "Objeto",
    "condiciones": "Condicion",
    "locations": "Location",
    "estados": "Estado",
}


def next_procedure_id(conn: Connection) -> str:  # Calcula el siguiente ID de procedimiento basado en los IDs numéricos existentes
    rows = conn.execute(text("SELECT id FROM procedures")).mappings().fetchall()
    nums = []
    for r in rows:
        iid = r["id"]
        if re.fullmatch(r"\d+", str(iid)):
            nums.append(int(iid))
    return str(max(nums) + 1 if nums else 1)


def next_task_id(conn: Connection, procedure_id: str) -> str:  # Genera el siguiente ID de tarea con formato '{procedure_id}.{número}'
    prefix = str(procedure_id)
    rows = conn.execute(
        text("SELECT id FROM tasks WHERE procedure_id = :procedure_id"),
        {"procedure_id": procedure_id},
    ).mappings().fetchall()
    nums = []
    for r in rows:
        iid = r["id"]
        m = re.fullmatch(re.escape(prefix) + r"\.(\d+)", str(iid))
        if m:
            nums.append(int(m.group(1)))
    return f"{prefix}.{max(nums) + 1 if nums else 1}"


def next_step_id(conn: Connection, task_id: str) -> str:  # Genera el siguiente ID de paso con formato '{task_id}.{número}'
    prefix = str(task_id)
    rows = conn.execute(
        text("SELECT id FROM steps WHERE task_id = :task_id"),
        {"task_id": task_id},
    ).mappings().fetchall()
    nums = []
    for r in rows:
        iid = r["id"]
        m = re.fullmatch(re.escape(prefix) + r"\.(\d+)", str(iid))
        if m:
            nums.append(int(m.group(1)))
    return f"{prefix}.{max(nums) + 1 if nums else 1}"


def validate_procedure(proc: Procedure) -> dict:  # Valida que el procedimiento tenga nombre, tareas con orden ascendente y pasos válidos
    if not proc.nombre:
        return {"valid": False, "reason": "El procedimiento requiere nombre."}
    task_orders = [task.orden for task in proc.tareas]
    if sorted(task_orders) != task_orders:
        return {"valid": False, "reason": "El orden de tareas debe ser ascendente."}

    for task in proc.tareas:
        if not task.nombre:
            return {"valid": False, "reason": f"La tarea {task.id} requiere nombre."}
        step_orders = [step.orden for step in task.pasos]
        if sorted(step_orders) != step_orders:
            return {"valid": False, "reason": f"El orden de pasos en la tarea {task.nombre} debe ser ascendente."}
        for step in task.pasos:
            if not step.nombre:
                return {"valid": False, "reason": f"El paso {step.id} requiere nombre."}
    return {"valid": True, "reason": "Procedimiento válido."}


def validate_state_transition(current_state: EstadoEnum, new_state: EstadoEnum) -> bool:  # Valida que la transición de estado sea permitida
    # Solo se permite: PENDIENTE -> EN_PROCESO, EN_PROCESO -> COMPLETADO, EN_PROCESO -> ERROR
    allowed_transitions = {
        EstadoEnum.PENDIENTE: [EstadoEnum.EN_PROCESO],
        EstadoEnum.EN_PROCESO: [EstadoEnum.COMPLETADO, EstadoEnum.ERROR],
        EstadoEnum.COMPLETADO: [],
        EstadoEnum.ERROR: [],
    }
    return new_state in allowed_transitions.get(current_state, [])


def now_iso() -> str:  # Marca de tiempo actual con precisión de segundos, para registrar cuándo se completó algo
    return datetime.now().isoformat(timespec="seconds")


def update_procedure_estado_cascada(conn: Connection, procedure_id: str) -> None:  # Actualiza el estado del procedimiento basado en sus tareas
    # Si todas las tareas están completadas, el procedimiento se marca como completado
    task_rows = conn.execute(
        text("SELECT estado FROM tasks WHERE procedure_id = :procedure_id"),
        {"procedure_id": procedure_id},
    ).mappings().fetchall()
    if not task_rows:
        return
    all_completed = all(row["estado"] == EstadoEnum.COMPLETADO.value for row in task_rows)
    if all_completed:
        conn.execute(
            text("UPDATE procedures SET estado = :estado, completado_en = :completado_en WHERE id = :id"),
            {"estado": EstadoEnum.COMPLETADO.value, "completado_en": now_iso(), "id": procedure_id},
        )


def update_task_estado_cascada(conn: Connection, task_id: str) -> None:  # Actualiza el estado de la tarea basado en sus pasos
    # Si todos los pasos están completados, la tarea se marca como completada
    step_rows = conn.execute(
        text("SELECT estado FROM steps WHERE task_id = :task_id"),
        {"task_id": task_id},
    ).mappings().fetchall()
    if not step_rows:
        return
    all_completed = all(row["estado"] == EstadoEnum.COMPLETADO.value for row in step_rows)
    if all_completed:
        conn.execute(
            text("UPDATE tasks SET estado = :estado, completado_en = :completado_en WHERE id = :id"),
            {"estado": EstadoEnum.COMPLETADO.value, "completado_en": now_iso(), "id": task_id},
        )
        # También actualizar el procedimiento padre
        task_row = conn.execute(
            text("SELECT procedure_id FROM tasks WHERE id = :id"), {"id": task_id}
        ).mappings().fetchone()
        if task_row:
            update_procedure_estado_cascada(conn, task_row["procedure_id"])


def extras_to_json(step: Step) -> str:  # Convierte las entidades extras de un paso (acciones, objetos, condiciones, etc.) a formato JSON
    return json.dumps(
        {
            "acciones": [a.dict() for a in step.acciones],
            "objetos": [o.dict() for o in step.objetos],
            "condiciones": [c.dict() for c in step.condiciones],
            "locations": [l.dict() for l in step.locations],
            "estados": [s.dict() for s in step.estados],
        },
        ensure_ascii=False,
    )


def extras_from_json(value: Optional[str]) -> dict:  # Convierte JSON a diccionario de entidades extras de un paso
    if not value:
        return {
            "acciones": [],
            "objetos": [],
            "condiciones": [],
            "locations": [],
            "estados": [],
        }
    return json.loads(value)


def resolve_catalog_list(kind: str, cls: type, cached_items: list[dict]) -> list:  # Resuelve en vivo contra Neo4j con fallback al snapshot cacheado en extras
    if not cached_items:
        return []
    label = CATALOG_LABEL_BY_KIND[kind]
    ids = [item["id"] for item in cached_items]
    fresh_map = resolve_items(label, ids)  # None si Neo4j no está disponible/configurado
    allowed_fields = set(cls.model_fields.keys())

    result = []
    for item in cached_items:
        fresh = None if fresh_map is None else fresh_map.get(item["id"])
        if fresh is not None:
            merged = {**item, **{k: v for k, v in fresh.items() if v is not None}, "stale": False}
        else:
            merged = {**item, "stale": True}
        result.append(cls(**{k: v for k, v in merged.items() if k in allowed_fields}))
    return result


def step_row_to_model(row: RowMapping) -> Step:  # Convierte una fila de base de datos a modelo Step con sus entidades asociadas
    extras = extras_from_json(row["extras"])
    return Step(
        id=row["id"],
        nombre=row["nombre"],
        informacion=row["informacion"],
        orden=row["orden"],
        estado=EstadoEnum(row["estado"] or EstadoEnum.PENDIENTE.value),
        completado_en=row["completado_en"],
        acciones=resolve_catalog_list("acciones", Action, extras.get("acciones", [])),
        objetos=resolve_catalog_list("objetos", ObjectEntry, extras.get("objetos", [])),
        condiciones=resolve_catalog_list("condiciones", Condition, extras.get("condiciones", [])),
        locations=resolve_catalog_list("locations", Location, extras.get("locations", [])),
        estados=resolve_catalog_list("estados", State, extras.get("estados", [])),
    )


def task_row_to_model(row: RowMapping, conn: Connection) -> Task:  # Convierte una fila de base de datos a modelo Task junto con sus pasos
    task_id = row["id"]
    step_rows = conn.execute(
        text("SELECT * FROM steps WHERE task_id = :task_id ORDER BY orden, nombre"),
        {"task_id": task_id},
    ).mappings().fetchall()
    pasos = [step_row_to_model(step_row) for step_row in step_rows]
    return Task(
        id=task_id,
        nombre=row["nombre"],
        informacion=row["informacion"],
        orden=row["orden"],
        estado=EstadoEnum(row["estado"] or EstadoEnum.PENDIENTE.value),
        completado_en=row["completado_en"],
        pasos=pasos,
    )


def procedure_row_to_model(row: RowMapping, conn: Connection) -> Procedure:  # Convierte una fila de base de datos a modelo Procedure completo con tareas y pasos
    procedure_id = row["id"]
    task_rows = conn.execute(
        text("SELECT * FROM tasks WHERE procedure_id = :procedure_id ORDER BY orden, nombre"),
        {"procedure_id": procedure_id},
    ).mappings().fetchall()
    tareas = [task_row_to_model(task_row, conn) for task_row in task_rows]
    return Procedure(
        id=procedure_id,
        nombre=row["nombre"],
        informacion=row["informacion"],
        estado=EstadoEnum(row["estado"] or EstadoEnum.PENDIENTE.value),
        completado_en=row["completado_en"],
        tareas=tareas,
    )


def get_procedure_model(procedure_id: str) -> Procedure:  # Obtiene un procedimiento completo de la base de datos
    with connect_db() as conn:
        row = conn.execute(
            text("SELECT * FROM procedures WHERE id = :id"), {"id": procedure_id}
        ).mappings().fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Procedimiento no encontrado")
        return procedure_row_to_model(row, conn)


def get_task_model(procedure_id: str, task_id: str) -> Task:  # Obtiene una tarea específica con todos sus pasos
    with connect_db() as conn:
        row = conn.execute(
            text("SELECT * FROM tasks WHERE id = :task_id AND procedure_id = :procedure_id"),
            {"task_id": task_id, "procedure_id": procedure_id},
        ).mappings().fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        return task_row_to_model(row, conn)


def reorder_tasks(conn: Connection, procedure_id: str, task_id: str, new_order: int) -> None:  # Reorganiza el orden de tareas dentro de un procedimiento
    rows = conn.execute(
        text("SELECT * FROM tasks WHERE procedure_id = :procedure_id ORDER BY orden, nombre"),
        {"procedure_id": procedure_id},
    ).mappings().fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado o sin tareas")

    task_rows = [row for row in rows if row["id"] != task_id]
    current = next((row for row in rows if row["id"] == task_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    new_order = max(1, min(new_order, len(rows)))
    task_rows.insert(new_order - 1, current)

    for index, row in enumerate(task_rows, start=1):
        if row["orden"] != index:
            conn.execute(
                text("UPDATE tasks SET orden = :orden WHERE id = :id AND procedure_id = :procedure_id"),
                {"orden": index, "id": row["id"], "procedure_id": procedure_id},
            )


def reorder_steps(conn: Connection, task_id: str, step_id: str, new_order: int) -> None:  # Reorganiza el orden de pasos dentro de una tarea
    rows = conn.execute(
        text("SELECT * FROM steps WHERE task_id = :task_id ORDER BY orden, nombre"),
        {"task_id": task_id},
    ).mappings().fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Tarea no encontrada o sin pasos")

    step_rows = [row for row in rows if row["id"] != step_id]
    current = next((row for row in rows if row["id"] == step_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail="Paso no encontrado")

    new_order = max(1, min(new_order, len(rows)))
    step_rows.insert(new_order - 1, current)

    for index, row in enumerate(step_rows, start=1):
        if row["orden"] != index:
            conn.execute(
                text("UPDATE steps SET orden = :orden WHERE id = :id AND task_id = :task_id"),
                {"orden": index, "id": row["id"], "task_id": task_id},
            )


def clamp_order(value: int, max_value: int) -> int:  # Limita un valor entre 1 y max_value
    return max(1, min(value, max_value))


def shift_task_orders(conn: Connection, procedure_id: str, target_order: int, exclude_task_id: Optional[str] = None) -> None:  # Desplaza el orden de tareas a partir de una posición determinada
    rows = conn.execute(
        text("SELECT id, orden FROM tasks WHERE procedure_id = :procedure_id ORDER BY orden, nombre"),
        {"procedure_id": procedure_id},
    ).mappings().fetchall()
    for row in rows:
        if exclude_task_id and row["id"] == exclude_task_id:
            continue
        if row["orden"] >= target_order:
            conn.execute(
                text("UPDATE tasks SET orden = orden + 1 WHERE id = :id AND procedure_id = :procedure_id"),
                {"id": row["id"], "procedure_id": procedure_id},
            )


def shift_step_orders(conn: Connection, task_id: str, target_order: int, exclude_step_id: Optional[str] = None) -> None:  # Desplaza el orden de pasos a partir de una posición determinada
    rows = conn.execute(
        text("SELECT id, orden FROM steps WHERE task_id = :task_id ORDER BY orden, nombre"),
        {"task_id": task_id},
    ).mappings().fetchall()
    for row in rows:
        if exclude_step_id and row["id"] == exclude_step_id:
            continue
        if row["orden"] >= target_order:
            conn.execute(
                text("UPDATE steps SET orden = orden + 1 WHERE id = :id AND task_id = :task_id"),
                {"id": row["id"], "task_id": task_id},
            )
