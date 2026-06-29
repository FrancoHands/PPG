from __future__ import annotations
from typing import List

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from crud import (
    clamp_order,
    extras_to_json,
    next_step_id,
    now_iso,
    reorder_steps,
    shift_step_orders,
    step_row_to_model,
    update_task_estado_cascada,
    validate_state_transition,
)
from database import connect_db
from exports import generate_exports_files
from models import ChangeEstadoBody, CreateStep, EditStep, EstadoEnum, ReorderBody, Step

router = APIRouter(prefix="/procedimientos/{procedure_id}/tareas/{task_id}/pasos", tags=["Pasos"])


@router.post("", response_model=Step, status_code=201)
def add_step(procedure_id: str, task_id: str, body: CreateStep):  # Endpoint POST: Crea un nuevo paso en una tarea con reordenamiento automático
    with connect_db() as conn:
        count_row = conn.execute(
            text("SELECT COUNT(*) AS count FROM steps WHERE task_id = :task_id"),
            {"task_id": task_id},
        ).mappings().fetchone()
        step_count = count_row["count"] if count_row else 0
        if body.orden <= 0:
            orden = step_count + 1
        else:
            orden = clamp_order(body.orden, step_count + 1)
        step_id = next_step_id(conn, task_id)
        step = Step(
            id=step_id,
            nombre=body.nombre,
            informacion=body.informacion,
            orden=orden,
            estado=EstadoEnum.PENDIENTE,
        )
        shift_step_orders(conn, task_id, orden)
        conn.execute(
            text(
                "INSERT INTO steps (id, task_id, nombre, informacion, orden, estado, extras) "
                "VALUES (:id, :task_id, :nombre, :informacion, :orden, :estado, :extras)"
            ),
            {
                "id": step.id,
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
    return get_step(procedure_id, task_id, step_id)


@router.get("", response_model=List[Step])
def list_steps(procedure_id: str, task_id: str):  # Endpoint GET: Lista todos los pasos de una tarea
    with connect_db() as conn:
        rows = conn.execute(
            text("SELECT * FROM steps WHERE task_id = :task_id ORDER BY orden, nombre"),
            {"task_id": task_id},
        ).mappings().fetchall()
        return [step_row_to_model(row) for row in rows]


@router.put("/{step_id}", response_model=Step)
def update_step(procedure_id: str, task_id: str, step_id: str, body: EditStep):  # Endpoint PUT: Actualiza los datos de un paso
    with connect_db() as conn:
        result = conn.execute(
            text(
                "UPDATE steps SET nombre = :nombre, informacion = :informacion "
                "WHERE id = :id AND task_id = :task_id"
            ),
            {"nombre": body.nombre, "informacion": body.informacion, "id": step_id, "task_id": task_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Paso no encontrado")
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
    return get_step(procedure_id, task_id, step_id)


@router.put("/{step_id}/orden", response_model=Step)
def reorder_step(procedure_id: str, task_id: str, step_id: str, body: ReorderBody):  # Endpoint PUT: Cambia el orden de un paso dentro de la tarea
    with connect_db() as conn:
        reorder_steps(conn, task_id, step_id, body.orden)
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
    return get_step(procedure_id, task_id, step_id)


@router.put("/{step_id}/estado", response_model=Step)
def change_step_estado(procedure_id: str, task_id: str, step_id: str, body: ChangeEstadoBody):  # Endpoint PUT: Cambia el estado de un paso
    with connect_db() as conn:
        row = conn.execute(
            text("SELECT estado FROM steps WHERE id = :step_id AND task_id = :task_id"),
            {"step_id": step_id, "task_id": task_id},
        ).mappings().fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Paso no encontrado")
        current_estado = EstadoEnum(row["estado"] or EstadoEnum.PENDIENTE.value)
        if not validate_state_transition(current_estado, body.estado):
            raise HTTPException(
                status_code=400,
                detail=f"Transición no permitida de {current_estado.value} a {body.estado.value}",
            )
        completado_en = now_iso() if body.estado == EstadoEnum.COMPLETADO else None
        conn.execute(
            text(
                "UPDATE steps SET estado = :estado, completado_en = :completado_en "
                "WHERE id = :id AND task_id = :task_id"
            ),
            {"estado": body.estado.value, "completado_en": completado_en, "id": step_id, "task_id": task_id},
        )
        update_task_estado_cascada(conn, task_id)
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
    return get_step(procedure_id, task_id, step_id)


@router.get("/{step_id}", response_model=Step)
def get_step(procedure_id: str, task_id: str, step_id: str):  # Endpoint GET: Obtiene un paso específico
    with connect_db() as conn:
        row = conn.execute(
            text("SELECT * FROM steps WHERE id = :step_id AND task_id = :task_id"),
            {"step_id": step_id, "task_id": task_id},
        ).mappings().fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Paso no encontrado")
        return step_row_to_model(row)


@router.delete("/{step_id}", status_code=204)
def delete_step(procedure_id: str, task_id: str, step_id: str):  # Endpoint DELETE: Elimina un paso de una tarea
    with connect_db() as conn:
        result = conn.execute(
            text("DELETE FROM steps WHERE id = :step_id AND task_id = :task_id"),
            {"step_id": step_id, "task_id": task_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Paso no encontrado")
        conn.commit()
    try:
        generate_exports_files()
    except Exception:
        pass
