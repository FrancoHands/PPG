from __future__ import annotations
from typing import List

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from crud import (
    clamp_order,
    get_task_model,
    next_task_id,
    now_iso,
    reorder_tasks,
    shift_task_orders,
    task_row_to_model,
    update_procedure_estado_cascada,
    validate_state_transition,
)
from database import connect_db
from exports import generate_exports_files
from models import ChangeEstadoBody, CreateTask, EditTask, EstadoEnum, ReorderBody, Task

router = APIRouter(prefix="/procedimientos/{procedure_id}/tareas", tags=["Tareas"])


@router.get("", response_model=List[Task])
def list_tasks(procedure_id: str):  # Endpoint GET: Lista todas las tareas de un procedimiento
    with connect_db() as conn:
        rows = conn.execute(
            text("SELECT * FROM tasks WHERE procedure_id = :procedure_id ORDER BY orden, nombre"),
            {"procedure_id": procedure_id},
        ).mappings().fetchall()
        return [task_row_to_model(row, conn) for row in rows]


@router.post("", response_model=Task, status_code=201)
def add_task(procedure_id: str, body: CreateTask):  # Endpoint POST: Crea una nueva tarea en un procedimiento con reordenamiento automático
    with connect_db() as conn:
        count_row = conn.execute(
            text("SELECT COUNT(*) AS count FROM tasks WHERE procedure_id = :procedure_id"),
            {"procedure_id": procedure_id},
        ).mappings().fetchone()
        task_count = count_row["count"] if count_row else 0
        if body.orden <= 0:
            orden = task_count + 1
        else:
            orden = clamp_order(body.orden, task_count + 1)
        task_id = next_task_id(conn, procedure_id)
        shift_task_orders(conn, procedure_id, orden)
        conn.execute(
            text(
                "INSERT INTO tasks (id, procedure_id, nombre, informacion, orden, estado) "
                "VALUES (:id, :procedure_id, :nombre, :informacion, :orden, :estado)"
            ),
            {
                "id": task_id,
                "procedure_id": procedure_id,
                "nombre": body.nombre,
                "informacion": body.informacion,
                "orden": orden,
                "estado": EstadoEnum.PENDIENTE.value,
            },
        )
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
    return get_task_model(procedure_id, task_id)


@router.get("/{task_id}", response_model=Task)
def get_task(procedure_id: str, task_id: str):  # Endpoint GET: Obtiene una tarea específica con todos sus pasos
    return get_task_model(procedure_id, task_id)


@router.put("/{task_id}", response_model=Task)
def update_task(procedure_id: str, task_id: str, body: EditTask):  # Endpoint PUT: Actualiza los datos de una tarea
    with connect_db() as conn:
        result = conn.execute(
            text(
                "UPDATE tasks SET nombre = :nombre, informacion = :informacion "
                "WHERE id = :id AND procedure_id = :procedure_id"
            ),
            {
                "nombre": body.nombre,
                "informacion": body.informacion,
                "id": task_id,
                "procedure_id": procedure_id,
            },
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
    return get_task_model(procedure_id, task_id)


@router.put("/{task_id}/orden", response_model=Task)
def reorder_task(procedure_id: str, task_id: str, body: ReorderBody):  # Endpoint PUT: Cambia el orden de una tarea dentro del procedimiento
    with connect_db() as conn:
        reorder_tasks(conn, procedure_id, task_id, body.orden)
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
    return get_task_model(procedure_id, task_id)


@router.put("/{task_id}/estado", response_model=Task)
def change_task_estado(procedure_id: str, task_id: str, body: ChangeEstadoBody):  # Endpoint PUT: Cambia el estado de una tarea
    with connect_db() as conn:
        row = conn.execute(
            text("SELECT estado FROM tasks WHERE id = :task_id AND procedure_id = :procedure_id"),
            {"task_id": task_id, "procedure_id": procedure_id},
        ).mappings().fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        current_estado = EstadoEnum(row["estado"] or EstadoEnum.PENDIENTE.value)
        if not validate_state_transition(current_estado, body.estado):
            raise HTTPException(
                status_code=400,
                detail=f"Transición no permitida de {current_estado.value} a {body.estado.value}",
            )
        completado_en = now_iso() if body.estado == EstadoEnum.COMPLETADO else None
        conn.execute(
            text(
                "UPDATE tasks SET estado = :estado, completado_en = :completado_en "
                "WHERE id = :id AND procedure_id = :procedure_id"
            ),
            {"estado": body.estado.value, "completado_en": completado_en, "id": task_id, "procedure_id": procedure_id},
        )
        update_procedure_estado_cascada(conn, procedure_id)
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
    return get_task_model(procedure_id, task_id)


@router.delete("/{task_id}", status_code=204)
def delete_task(procedure_id: str, task_id: str):  # Endpoint DELETE: Elimina una tarea y sus pasos asociados
    with connect_db() as conn:
        conn.execute(text("DELETE FROM steps WHERE task_id = :task_id"), {"task_id": task_id})
        result = conn.execute(
            text("DELETE FROM tasks WHERE id = :task_id AND procedure_id = :procedure_id"),
            {"task_id": task_id, "procedure_id": procedure_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
