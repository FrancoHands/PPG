from __future__ import annotations
import copy
from typing import List

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from crud import (
    extras_to_json,
    get_procedure_model,
    next_procedure_id,
    now_iso,
    procedure_row_to_model,
    validate_procedure,
    validate_state_transition,
)
from database import connect_db
from exports import generate_exports_files
from models import ChangeEstadoBody, CreateProcedure, EstadoEnum, Procedure, new_uuid

router = APIRouter(prefix="/procedimientos", tags=["Procedimientos"])


@router.get("", response_model=List[Procedure])
def list_procedures():  # Endpoint GET: Lista todos los procedimientos
    with connect_db() as conn:
        rows = conn.execute(text("SELECT * FROM procedures ORDER BY nombre")).mappings().fetchall()
        return [procedure_row_to_model(row, conn) for row in rows]


@router.post("", response_model=Procedure, status_code=201)
def create_procedure(body: CreateProcedure):  # Endpoint POST: Crea un nuevo procedimiento
    with connect_db() as conn:
        procedure_id = next_procedure_id(conn)
        conn.execute(
            text(
                "INSERT INTO procedures (id, nombre, informacion, estado) "
                "VALUES (:id, :nombre, :informacion, :estado)"
            ),
            {
                "id": procedure_id,
                "nombre": body.nombre,
                "informacion": body.informacion,
                "estado": EstadoEnum.PENDIENTE.value,
            },
        )
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
    return get_procedure_model(procedure_id)


@router.get("/{procedure_id}", response_model=Procedure)
def get_procedure(procedure_id: str):  # Endpoint GET: Obtiene un procedimiento específico con todas sus tareas y pasos
    return get_procedure_model(procedure_id)


@router.put("/{procedure_id}", response_model=Procedure)
def update_procedure(procedure_id: str, body: CreateProcedure):  # Endpoint PUT: Actualiza los datos de un procedimiento
    with connect_db() as conn:
        result = conn.execute(
            text("UPDATE procedures SET nombre = :nombre, informacion = :informacion WHERE id = :id"),
            {"nombre": body.nombre, "informacion": body.informacion, "id": procedure_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Procedimiento no encontrado")
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
    return get_procedure_model(procedure_id)


@router.delete("/{procedure_id}", status_code=204)
def delete_procedure(procedure_id: str):  # Endpoint DELETE: Elimina un procedimiento y sus tareas y pasos asociados
    with connect_db() as conn:
        # delete dependent steps and tasks manually to ensure hierarchical deletion
        conn.execute(
            text(
                "DELETE FROM steps WHERE task_id IN "
                "(SELECT id FROM tasks WHERE procedure_id = :procedure_id)"
            ),
            {"procedure_id": procedure_id},
        )
        conn.execute(
            text("DELETE FROM tasks WHERE procedure_id = :procedure_id"),
            {"procedure_id": procedure_id},
        )
        result = conn.execute(
            text("DELETE FROM procedures WHERE id = :id"), {"id": procedure_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Procedimiento no encontrado")
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass


@router.post("/{procedure_id}/clonar", response_model=Procedure)
def clone_procedure(procedure_id: str):  # Endpoint POST: Clona un procedimiento con todas sus tareas y pasos, generando nuevos IDs
    original = get_procedure_model(procedure_id)
    clone = copy.deepcopy(original)
    with connect_db() as conn:
        new_proc_id = next_procedure_id(conn)
        conn.execute(
            text(
                "INSERT INTO procedures (id, nombre, informacion, estado) "
                "VALUES (:id, :nombre, :informacion, :estado)"
            ),
            {
                "id": new_proc_id,
                "nombre": f"{clone.nombre} (clon)",
                "informacion": clone.informacion,
                "estado": EstadoEnum.PENDIENTE.value,
            },
        )
        # insert tasks and steps with hierarchical ids
        for ti, task in enumerate(clone.tareas, start=1):
            task_id = f"{new_proc_id}.{ti}"
            conn.execute(
                text(
                    "INSERT INTO tasks (id, procedure_id, nombre, informacion, orden, estado) "
                    "VALUES (:id, :procedure_id, :nombre, :informacion, :orden, :estado)"
                ),
                {
                    "id": task_id,
                    "procedure_id": new_proc_id,
                    "nombre": task.nombre,
                    "informacion": task.informacion,
                    "orden": task.orden,
                    "estado": EstadoEnum.PENDIENTE.value,
                },
            )
            for stepi, step in enumerate(task.pasos, start=1):
                step_id = f"{task_id}.{stepi}"
                # regenerate inner item ids to avoid collisions
                for item_list in [step.acciones, step.objetos, step.condiciones, step.locations, step.estados]:
                    for item in item_list:
                        item.id = new_uuid()
                conn.execute(
                    text(
                        "INSERT INTO steps (id, task_id, nombre, informacion, orden, estado, extras) "
                        "VALUES (:id, :task_id, :nombre, :informacion, :orden, :estado, :extras)"
                    ),
                    {
                        "id": step_id,
                        "task_id": task_id,
                        "nombre": step.nombre,
                        "informacion": step.informacion,
                        "orden": step.orden,
                        "estado": EstadoEnum.PENDIENTE.value,
                        "extras": extras_to_json(step),
                    },
                )
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
    return get_procedure_model(new_proc_id)


@router.get("/{procedure_id}/validar")
def validate_procedure_endpoint(procedure_id: str):  # Endpoint GET: Valida un procedimiento y devuelve el resultado
    proc = get_procedure_model(procedure_id)
    return validate_procedure(proc)


@router.put("/{procedure_id}/estado", response_model=Procedure)
def change_procedure_estado(procedure_id: str, body: ChangeEstadoBody):  # Endpoint PUT: Cambia el estado de un procedimiento
    with connect_db() as conn:
        row = conn.execute(
            text("SELECT estado FROM procedures WHERE id = :id"), {"id": procedure_id}
        ).mappings().fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Procedimiento no encontrado")
        current_estado = EstadoEnum(row["estado"] or EstadoEnum.PENDIENTE.value)
        if not validate_state_transition(current_estado, body.estado):
            raise HTTPException(
                status_code=400,
                detail=f"Transición no permitida de {current_estado.value} a {body.estado.value}",
            )
        completado_en = now_iso() if body.estado == EstadoEnum.COMPLETADO else None
        conn.execute(
            text("UPDATE procedures SET estado = :estado, completado_en = :completado_en WHERE id = :id"),
            {"estado": body.estado.value, "completado_en": completado_en, "id": procedure_id},
        )
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
    return get_procedure_model(procedure_id)
