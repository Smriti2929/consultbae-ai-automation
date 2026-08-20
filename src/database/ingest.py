"""Rebuild the canonical SQLite database from immutable raw CSV files."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.database.db import (
    DEFAULT_DATABASE_PATH,
    initialize_schema,
    open_database,
    summary_counts,
)
from src.matching.entity_resolution import (
    INVALID_SOURCE_RECORD,
    MATCHED_HIGH_CONFIDENCE,
    NEW_ENTITY,
    Entity,
    MatchDecision,
)
from src.matching.generate_report import generate_decisions


SOURCE_PRIORITY = {
    "source1_naukri_applicants.csv": 1,
    "source2_gig_workers.csv": 2,
    "source3_cbnexus_contacts.csv": 3,
}

CONFIDENCE_BY_STATUS = {
    MATCHED_HIGH_CONFIDENCE: "HIGH",
    NEW_ENTITY: "NEW",
    "AMBIGUOUS_REVIEW": "REVIEW_REQUIRED",
    INVALID_SOURCE_RECORD: "INVALID",
}


def normalized_display_name(value: str | None) -> str | None:
    """Trim/collapse whitespace for display without changing spelling or case."""
    return re.sub(r"\s+", " ", value.strip()) if value and value.strip() else None


def ordered_decisions(decisions: list[MatchDecision]) -> list[MatchDecision]:
    return sorted(
        decisions,
        key=lambda item: (
            SOURCE_PRIORITY[item.record.source_file],
            item.record.source_row,
        ),
    )


def first_present(decisions: list[MatchDecision], attribute: str) -> str | None:
    for decision in ordered_decisions(decisions):
        value = getattr(decision.record, attribute)
        if value:
            return value
    return None


def conflict_values(entity: Entity) -> dict[str, list[str]]:
    """Expose multiple valid identity values instead of hiding them."""
    possible_conflicts = {
        "normalized_names": sorted(entity.names),
        "normalized_emails": sorted(entity.emails),
        "normalized_phones": sorted(entity.phones),
        "normalized_cities": sorted(entity.cities),
    }
    return {
        field: values for field, values in possible_conflicts.items() if len(values) > 1
    }


def insert_persons(
    connection,
    entities: dict[str, Entity],
    attached: dict[str, list[MatchDecision]],
    timestamp: str,
) -> dict[str, int]:
    """Insert one person for each safe Phase 2 provisional entity."""
    person_ids: dict[str, int] = {}
    for provisional_id in sorted(entities):
        decisions = attached[provisional_id]
        canonical_name = normalized_display_name(first_present(decisions, "raw_name"))
        canonical_email = first_present(decisions, "normalized_email")
        canonical_phone = first_present(decisions, "normalized_phone")
        canonical_city = first_present(decisions, "normalized_city")
        cursor = connection.execute(
            """
            INSERT INTO persons (
                provisional_entity_id, canonical_name, canonical_email,
                canonical_phone, canonical_city, canonical_conflicts_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provisional_id,
                canonical_name,
                canonical_email,
                canonical_phone,
                canonical_city,
                json.dumps(conflict_values(entities[provisional_id]), ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
        person_ids[provisional_id] = cursor.lastrowid
    return person_ids


def insert_source_records(
    connection,
    decisions: list[MatchDecision],
    person_ids: dict[str, int],
    timestamp: str,
) -> None:
    """Insert every source row, including ambiguous and invalid records."""
    for decision in decisions:
        record = decision.record
        person_id = None
        if decision.status in (NEW_ENTITY, MATCHED_HIGH_CONFIDENCE):
            person_id = person_ids[decision.matched_entity_id]  # type: ignore[index]

        connection.execute(
            """
            INSERT INTO source_records (
                source_system, source_filename, source_row_number, person_id,
                match_status, match_confidence, match_evidence_json, match_reason,
                candidate_entity_ids_json, conflicting_evidence_json,
                raw_name, raw_email, raw_phone, raw_city,
                normalized_name, normalized_email, normalized_phone,
                normalized_city, raw_record_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.source_system,
                record.source_file,
                record.source_row,
                person_id,
                decision.status,
                CONFIDENCE_BY_STATUS[decision.status],
                json.dumps(decision.evidence, ensure_ascii=False),
                decision.reason,
                json.dumps(decision.candidate_entity_ids, ensure_ascii=False),
                json.dumps(decision.conflicting_evidence, ensure_ascii=False),
                record.raw_name,
                record.raw_email,
                record.raw_phone,
                record.raw_city,
                record.normalized_name,
                record.normalized_email,
                record.normalized_phone,
                record.normalized_city,
                json.dumps(record.raw_record, ensure_ascii=False),
                timestamp,
            ),
        )


def validate_database(connection, expected_records: int, expected_persons: int) -> None:
    counts = summary_counts(connection)
    if counts["source_records"] != expected_records:
        raise ValueError("Database does not contain every source record.")
    if counts["canonical_persons"] != expected_persons:
        raise ValueError("Database person count differs from safe provisional entities.")
    if counts["linked_source_records"] + counts["unresolved_source_records"] != expected_records:
        raise ValueError("Linked and unresolved source-record counts do not balance.")
    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise ValueError(f"Foreign-key validation failed: {foreign_key_errors}")


def build_database(database_path: Path = DEFAULT_DATABASE_PATH) -> dict[str, int]:
    """Build in a temporary file, validate, then replace the target atomically."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        existing_connection = open_database(database_path)
        try:
            table_exists = existing_connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'audio_submissions'"
            ).fetchone()
            submission_count = (
                existing_connection.execute("SELECT COUNT(*) FROM audio_submissions").fetchone()[0]
                if table_exists
                else 0
            )
        finally:
            existing_connection.close()
        if submission_count:
            raise RuntimeError(
                "Database rebuild refused: audio_submissions contains worker data. "
                "Back up or migrate those submissions before rebuilding."
            )
    temporary_path = database_path.with_suffix(database_path.suffix + ".building")
    if temporary_path.exists():
        temporary_path.unlink()

    decisions, matcher = generate_decisions()
    attached: dict[str, list[MatchDecision]] = defaultdict(list)
    for decision in decisions:
        if decision.status in (NEW_ENTITY, MATCHED_HIGH_CONFIDENCE):
            attached[decision.matched_entity_id].append(decision)  # type: ignore[index]

    timestamp = datetime.now(timezone.utc).isoformat()
    connection = open_database(temporary_path)
    try:
        initialize_schema(connection)
        with connection:
            person_ids = insert_persons(connection, matcher.entities, attached, timestamp)
            insert_source_records(connection, decisions, person_ids, timestamp)
        validate_database(connection, len(decisions), len(matcher.entities))
    finally:
        connection.close()

    temporary_path.replace(database_path)
    with open_database(database_path) as final_connection:
        return summary_counts(final_connection)


def main() -> None:
    counts = build_database()
    print(f"Database rebuilt: {DEFAULT_DATABASE_PATH}")
    print(f"Raw source records processed: {counts['source_records']}")
    print(f"Canonical persons created: {counts['canonical_persons']}")
    print(f"High-confidence matched records: {counts.get(MATCHED_HIGH_CONFIDENCE, 0)}")
    print(f"Ambiguous records: {counts.get('AMBIGUOUS_REVIEW', 0)}")
    print(f"Invalid records: {counts.get(INVALID_SOURCE_RECORD, 0)}")
    print(f"Source records with person IDs: {counts['linked_source_records']}")
    print(f"Unresolved source records: {counts['unresolved_source_records']}")


if __name__ == "__main__":
    main()
