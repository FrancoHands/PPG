"""Diagnóstico de conexión directa a Neo4j, sin la capa de fallback de clients/neo4j_client.py.
Muestra el error real (auth, URI, red, timeout) en vez de tragarlo.
Uso, desde backend/: python scripts/diagnose_neo4j.py
"""
from __future__ import annotations

import os
import time

from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_USER = os.environ.get("NEO4J_USER")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

print(f"NEO4J_URI={NEO4J_URI!r}")
print(f"NEO4J_USER={NEO4J_USER!r}")
print(f"NEO4J_DATABASE={NEO4J_DATABASE!r}")
print(f"NEO4J_PASSWORD configurada: {bool(NEO4J_PASSWORD)}")

t0 = time.monotonic()
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
try:
    driver.verify_connectivity()
    print(f"verify_connectivity OK en {time.monotonic() - t0:.2f}s")

    t0 = time.monotonic()
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("MATCH (n:Accion {id: 'a1'}) RETURN n.id AS id, n.nombre AS nombre")
        rows = list(result)
        print(f"query OK en {time.monotonic() - t0:.2f}s -> {rows}")
finally:
    driver.close()
