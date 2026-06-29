from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table, Text, create_engine, event

DB_PATH = Path(__file__).with_name("data.db")

# Por defecto usa SQLite local. El día que se instale PostgreSQL, alcanza con
# definir DATABASE_URL (ej: postgresql://usuario:clave@host/dbname) sin tocar
# main.py: las queries usan SQL estándar con bind params, no sintaxis de SQLite.
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


metadata = MetaData()

procedures = Table(
    "procedures",
    metadata,
    Column("id", Text, primary_key=True),
    Column("nombre", Text, nullable=False),
    Column("informacion", Text),
    Column("estado", Text, server_default="PENDIENTE"),
    Column("completado_en", Text),
)

tasks = Table(
    "tasks",
    metadata,
    Column("id", Text, primary_key=True),
    Column("procedure_id", Text, ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False),
    Column("nombre", Text, nullable=False),
    Column("informacion", Text),
    Column("orden", Integer, nullable=False),
    Column("estado", Text, server_default="PENDIENTE"),
    Column("completado_en", Text),
)

steps = Table(
    "steps",
    metadata,
    Column("id", Text, primary_key=True),
    Column("task_id", Text, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
    Column("nombre", Text, nullable=False),
    Column("informacion", Text),
    Column("orden", Integer, nullable=False),
    Column("estado", Text, server_default="PENDIENTE"),
    Column("extras", Text),
    Column("completado_en", Text),
)


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    metadata.create_all(engine)


def connect_db():
    return engine.connect()
