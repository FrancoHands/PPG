"""Pobla el catálogo Neo4j con nodos de ejemplo para probar la resolución en vivo.

Requiere NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD (y opcionalmente NEO4J_DATABASE)
en el entorno. Uso, desde backend/: python scripts/seed_neo4j.py
"""
from __future__ import annotations

import json
import os
import sys

from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_USER = os.environ.get("NEO4J_USER")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

# Labels y propiedades alineadas con CATALOG_LABEL_BY_KIND en backend/crud.py
SAMPLE_NODES = {
    "Accion": [
        {
            "id": "a1",
            "nombre": "Cortar",
            "informacion": "Cortar el material con la herramienta indicada",
            "tipo": "manual",
            "parametros": json.dumps({"herramienta": "tijera"}),
        },
        {
            "id": "a2",
            "nombre": "Soldar",
            "informacion": "Unir dos piezas metálicas por fusión",
            "tipo": "manual",
            "parametros": json.dumps({"temperatura": "350C"}),
        },
    ],
    "Objeto": [
        {"id": "o1", "nombre": "Tornillo M4", "informacion": "Tornillo métrico de 4mm"},
        {"id": "o2", "nombre": "Placa base", "informacion": "Placa de soporte principal"},
    ],
    "Condicion": [
        {"id": "c1", "nombre": "Temperatura ambiente > 20°C", "informacion": None},
        {"id": "c2", "nombre": "Pieza limpia y seca", "informacion": None},
    ],
    "Location": [
        {"id": "l1", "nombre": "Almacén A", "informacion": "Zona de materiales crudos"},
        {"id": "l2", "nombre": "Línea de ensamblaje 1", "informacion": None},
    ],
    "Estado": [
        {"id": "e1", "nombre": "Disponible", "informacion": None},
        {"id": "e2", "nombre": "En mantenimiento", "informacion": None},
    ],
}


def seed() -> None:
    if not NEO4J_URI or not NEO4J_USER or not NEO4J_PASSWORD:
        sys.exit("Faltan NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD en el entorno.")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            for label in SAMPLE_NODES:
                session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE")
            for label, nodes in SAMPLE_NODES.items():
                for node in nodes:
                    session.run(f"MERGE (n:{label} {{id: $id}}) SET n += $props", id=node["id"], props=node)
                print(f"{label}: {len(nodes)} nodos sembrados")
    finally:
        driver.close()


if __name__ == "__main__":
    seed()
