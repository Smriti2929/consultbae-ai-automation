"""Small SQLite connection, schema, and summary helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "processed" / "consultbae.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def open_database(path: Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    """Open SQLite with named rows and foreign-key checks enabled."""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create the Phase 3 schema in an empty database."""
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def summary_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Return the principal ingestion validation counts."""
    counts = {
        "canonical_persons": connection.execute("SELECT COUNT(*) FROM persons").fetchone()[0],
        "source_records": connection.execute("SELECT COUNT(*) FROM source_records").fetchone()[0],
        "linked_source_records": connection.execute(
            "SELECT COUNT(*) FROM source_records WHERE person_id IS NOT NULL"
        ).fetchone()[0],
        "unresolved_source_records": connection.execute(
            "SELECT COUNT(*) FROM source_records WHERE person_id IS NULL"
        ).fetchone()[0],
    }
    status_rows = connection.execute(
        "SELECT match_status, COUNT(*) AS count FROM source_records GROUP BY match_status"
    ).fetchall()
    counts.update({row["match_status"]: row["count"] for row in status_rows})
    return counts

