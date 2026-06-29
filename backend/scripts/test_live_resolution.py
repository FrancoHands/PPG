"""Prueba de extremo a extremo: resolución en vivo contra Neo4j con fallback al cache local.

Requiere que el catálogo ya esté poblado (ver scripts/seed_neo4j.py) y las env
vars NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD activas en esta sesión.
Uso, desde backend/: python scripts/test_live_resolution.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

import crud
from clients.neo4j_client import is_enabled
from database import connect_db, init_db

init_db()

CACHED_PLACEHOLDER = "(nombre cacheado desde antes, sin contacto con Neo4j)"

with connect_db() as conn:
    proc_id = crud.next_procedure_id(conn)
    conn.execute(
        text("INSERT INTO procedures (id, nombre, estado) VALUES (:id, 'Prueba Neo4j', 'PENDIENTE')"),
        {"id": proc_id},
    )
    task_id = crud.next_task_id(conn, proc_id)
    conn.execute(
        text(
            "INSERT INTO tasks (id, procedure_id, nombre, orden, estado) "
            "VALUES (:id, :pid, 'Tarea prueba', 1, 'PENDIENTE')"
        ),
        {"id": task_id, "pid": proc_id},
    )
    step_id = crud.next_step_id(conn, task_id)
    extras_json = json.dumps(
        {
            "acciones": [
                {
                    "id": "a1",
                    "nombre": CACHED_PLACEHOLDER,
                    "informacion": None,
                    "tipo": None,
                    "parametros": {},
                    "stale": False,
                }
            ],
            "objetos": [],
            "condiciones": [],
            "locations": [],
            "estados": [],
        },
        ensure_ascii=False,
    )
    conn.execute(
        text(
            "INSERT INTO steps (id, task_id, nombre, orden, estado, extras) "
            "VALUES (:id, :tid, 'Paso prueba', 1, 'PENDIENTE', :extras)"
        ),
        {"id": step_id, "tid": task_id, "extras": extras_json},
    )
    conn.commit()

    print(f"Catálogo Neo4j configurado (NEO4J_URI presente): {is_enabled()}")
    row = conn.execute(text("SELECT * FROM steps WHERE id = :id"), {"id": step_id}).mappings().fetchone()
    step = crud.step_row_to_model(row)
    accion = step.acciones[0]
    print(f"accion.id        = {accion.id}")
    print(f"accion.nombre     = {accion.nombre}")
    print(f"accion.tipo       = {accion.tipo}")
    print(f"accion.parametros = {accion.parametros}")
    print(f"accion.stale      = {accion.stale}")

    if accion.stale:
        print("\n-> stale=True: no se pudo resolver en vivo, se mantuvo el nombre cacheado.")
    else:
        print("\n-> stale=False: se resolvió en vivo contra Neo4j (nombre/tipo/parametros frescos).")
