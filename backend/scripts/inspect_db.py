import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from database import connect_db

with connect_db() as conn:
    print('TABLE definitions:')
    for table in ['procedures', 'tasks', 'steps']:
        # sqlite_master es específico de SQLite; al migrar de motor esta sección debe adaptarse
        row = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name = :name"),
            {"name": table},
        ).mappings().fetchone()
        print(f'-- {table} --')
        print(row["sql"] if row else 'MISSING')
        print()

    for table, cols in [
        ('procedures', ['id', 'nombre']),
        ('tasks', ['id', 'procedure_id', 'nombre']),
        ('steps', ['id', 'task_id', 'nombre']),
    ]:
        print(f'ROWS in {table}:')
        rows = conn.execute(text(f'SELECT {",".join(cols)} FROM {table}')).mappings().fetchall()
        for row in rows:
            print({col: row[col] for col in cols})
        print()

    print('ORPHAN tasks:')
    orphan_tasks = conn.execute(
        text(
            "SELECT t.id, t.procedure_id, t.nombre FROM tasks t "
            "LEFT JOIN procedures p ON t.procedure_id = p.id WHERE p.id IS NULL"
        )
    ).mappings().fetchall()
    for row in orphan_tasks:
        print(dict(row))
    print()

    print('ORPHAN steps:')
    orphan_steps = conn.execute(
        text(
            "SELECT s.id, s.task_id, s.nombre FROM steps s "
            "LEFT JOIN tasks t ON s.task_id = t.id WHERE t.id IS NULL"
        )
    ).mappings().fetchall()
    for row in orphan_steps:
        print(dict(row))
