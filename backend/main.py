from __future__ import annotations

from fastapi import FastAPI

from clients.neo4j_client import close_driver
from database import init_db
from exports import generate_exports_files
from routers import pasos, procedimientos, tareas

app = FastAPI(
    title="Procedimientos Backend",
    description="API local para procedimientos, tareas, pasos y acciones basada en los requisitos proporcionados.",
    version="0.1.0",
)

app.include_router(procedimientos.router)
app.include_router(tareas.router)
app.include_router(pasos.router)


@app.post("/exports/regenerar")
def regenerate_exports():  # Endpoint POST: Regenera los archivos de exportación manualmente
    p, t, s, pf = generate_exports_files()
    return {"procedures": p, "tasks": t, "steps": s, "procedures_full": pf}


@app.on_event("startup")
def startup_event():  # Se ejecuta al iniciar la aplicación: inicializa la base de datos
    init_db()


@app.on_event("shutdown")
def shutdown_event():  # Cierra la conexión con el catálogo Neo4j (si estaba abierta)
    close_driver()
