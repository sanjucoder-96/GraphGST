"""db.py — Neo4j driver singleton. Configure via environment variables.

Environment
-----------
NEO4J_URI       bolt://localhost:7687  (local/docker)  |  neo4j+s://<id>.databases.neo4j.io  (Aura)
NEO4J_USERNAME  database user
NEO4J_PASSWORD  database password
NEO4J_DATABASE  target database name. Local/docker Neo4j uses "neo4j"; an Aura
                instance exposes a NAMED database (often the instance id, e.g.
                "38828ec0"). Empty ⇒ the driver's home database for the user.

`.env` (if present next to this file) is loaded on import so the running app,
the test-suite, and one-off scripts all see the same configuration without the
caller having to export variables by hand. Real values live only in the
gitignored `.env`; `.env.example` documents the shape.
"""
import os

try:  # best-effort .env loading; never fatal if python-dotenv is absent
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except Exception:  # pragma: no cover - dotenv is a normal dependency
    pass

from neo4j import GraphDatabase

_driver = None


def database_name():
    """The configured target database, or None to use the driver's home DB."""
    db = os.getenv("NEO4J_DATABASE", "").strip()
    return db or None


def get_driver():
    global _driver
    if _driver is None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USERNAME", "neo4j")
        pw = os.getenv("NEO4J_PASSWORD", "password")
        _driver = GraphDatabase.driver(uri, auth=(user, pw))
    return _driver


def close_driver():
    global _driver
    if _driver:
        _driver.close()
        _driver = None


def run_query(cypher, params=None):
    """Read (auto-commit) — every session is pinned to the configured database."""
    with get_driver().session(database=database_name()) as s:
        return [dict(r) for r in s.run(cypher, params or {})]


def run_write(cypher, params=None):
    """Write in a managed transaction (retried by the driver on transient errors)."""
    with get_driver().session(database=database_name()) as s:
        return s.execute_write(lambda tx: list(tx.run(cypher, params or {})))
