from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_USER = os.environ.get("NEO4J_USER")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")
NEO4J_TIMEOUT_SECONDS = float(os.environ.get("NEO4J_TIMEOUT_SECONDS", "2"))

# Labels permitidas en el catálogo, fijas en código: una label de Neo4j no se
# puede parametrizar como bind param, así que solo se interpola este whitelist.
CATALOG_LABELS = {"Accion", "Objeto", "Condicion", "Location", "Estado"}

_driver = None
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="neo4j-resolve")


def is_enabled() -> bool:  # El catálogo Neo4j es opcional: sin URI configurada, todo cae al cache local
    return bool(NEO4J_URI)


def _get_driver():
    global _driver
    if not is_enabled():
        return None
    if _driver is None:
        try:
            _driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
                connection_timeout=NEO4J_TIMEOUT_SECONDS,
            )
        except Exception:
            _driver = None
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def _record_to_dict(record) -> dict:
    data = dict(record)
    parametros = data.get("parametros")
    if isinstance(parametros, str):
        try:
            data["parametros"] = json.loads(parametros)
        except ValueError:
            pass
    return data


def _resolve_items_sync(label: str, ids: list[str]) -> dict[str, dict]:
    driver = _get_driver()
    if driver is None:
        raise Neo4jError("Neo4j no configurado")
    query = (
        f"MATCH (n:{label}) WHERE n.id IN $ids "
        "RETURN n.id AS id, n.nombre AS nombre, n.informacion AS informacion, "
        "n.tipo AS tipo, n.parametros AS parametros"
    )
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query, ids=ids)
        return {record["id"]: _record_to_dict(record) for record in result}


def resolve_items(label: str, ids: list[str]) -> Optional[dict[str, dict]]:
    """Resuelve nodos del catálogo por id con timeout duro.

    Devuelve None (en vez de lanzar) si el catálogo no está configurado, no
    responde a tiempo, o la conexión se cae — el caller debe interpretarlo
    como "usar el último snapshot cacheado".
    """
    if not ids or label not in CATALOG_LABELS or not is_enabled():
        return None
    future = _executor.submit(_resolve_items_sync, label, ids)
    try:
        return future.result(timeout=NEO4J_TIMEOUT_SECONDS)
    except Exception:
        future.cancel()
        return None
