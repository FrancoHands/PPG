import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from database import connect_db

with connect_db() as conn:
    orphan_steps = conn.execute(
        text(
            "SELECT s.id, s.task_id, s.nombre FROM steps s "
            "LEFT JOIN tasks t ON s.task_id = t.id WHERE t.id IS NULL"
        )
    ).mappings().fetchall()
    orphan_tasks = conn.execute(
        text(
            "SELECT t.id, t.procedure_id, t.nombre FROM tasks t "
            "LEFT JOIN procedures p ON t.procedure_id = p.id WHERE p.id IS NULL"
        )
    ).mappings().fetchall()

    if orphan_steps:
        conn.execute(text("DELETE FROM steps WHERE id = :id"), [{"id": row["id"]} for row in orphan_steps])
    if orphan_tasks:
        conn.execute(text("DELETE FROM tasks WHERE id = :id"), [{"id": row["id"]} for row in orphan_tasks])
    conn.commit()

print(f"Removed {len(orphan_steps)} orphan steps and {len(orphan_tasks)} orphan tasks.")
if orphan_tasks:
    print("Orphan task IDs removed:")
    for row in orphan_tasks:
        print(f"- {row['id']} (procedure_id={row['procedure_id']})")
if orphan_steps:
    print("Orphan step IDs removed:")
    for row in orphan_steps:
        print(f"- {row['id']} (task_id={row['task_id']})")
