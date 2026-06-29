from __future__ import annotations
import json
from pathlib import Path

from sqlalchemy import text

from database import connect_db


def _write_json(path: Path, data):  # Escribe datos a un archivo JSON con formato legible
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_exports_files() -> tuple[int, int, int, int]:  # Genera archivos JSON de exportación (procedimientos, tareas, pasos y procedimientos completos)
    root = Path(__file__).parent
    exports_dir = root / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    with connect_db() as conn:
        proc_rows = conn.execute(text("SELECT * FROM procedures ORDER BY id")).mappings().fetchall()
        procedures = [dict(r) for r in proc_rows]

        task_rows = conn.execute(
            text("SELECT * FROM tasks ORDER BY procedure_id, orden, nombre")
        ).mappings().fetchall()
        tasks = []
        task_map = {}
        for r in task_rows:
            row = dict(r)
            procedure_id = row.pop('procedure_id', None)
            tasks.append(row)
            task_map[row['id']] = dict(row, pasos=[], procedure_id=procedure_id)

        step_rows = conn.execute(
            text("SELECT * FROM steps ORDER BY task_id, orden, nombre")
        ).mappings().fetchall()
        steps = []
        for r in step_rows:
            extras = r["extras"]
            extras_json = None
            if extras:
                try:
                    extras_json = json.loads(extras)
                except Exception:
                    extras_json = None
            row = dict(r)
            task_id = row.pop("task_id", None)
            row["extras_json"] = extras_json
            steps.append(row)
            if task_id in task_map:
                task_map[task_id]['pasos'].append(row)

        procedure_map = {proc['id']: dict(proc, tareas=[]) for proc in procedures}
        for task in task_map.values():
            procedure_id = task.pop('procedure_id', None)
            if procedure_id in procedure_map:
                procedure_map[procedure_id]['tareas'].append(task)
        procedures_full = list(procedure_map.values())

    _write_json(exports_dir / "procedures.json", procedures)
    _write_json(exports_dir / "tasks.json", tasks)
    _write_json(exports_dir / "steps.json", steps)
    _write_json(exports_dir / "procedures_full.json", procedures_full)

    return (len(procedures), len(tasks), len(steps), len(procedures_full))
