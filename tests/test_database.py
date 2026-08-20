import json
import sqlite3
from pathlib import Path

import pytest

from src.database.db import open_database, summary_counts
from src.database.ingest import build_database


@pytest.fixture()
def built_database(tmp_path: Path) -> Path:
    path = tmp_path / "consultbae-test.db"
    build_database(path)
    return path


def test_schema_initialization(built_database: Path) -> None:
    with open_database(built_database) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"persons", "source_records", "audio_submissions"}.issubset(tables)


def test_rebuild_refuses_to_discard_audio_submissions(built_database: Path) -> None:
    with open_database(built_database) as connection:
        person_id = connection.execute("SELECT id FROM persons LIMIT 1").fetchone()[0]
        connection.execute(
            """
            INSERT INTO audio_submissions (
                person_id, submitted_name, submitted_phone, normalized_name,
                normalized_phone, original_filename, stored_filename,
                file_path, created_at
            ) VALUES (?, 'Test', '9000000000', 'test', '9000000000',
                      'test.wav', 'unique.wav', 'uploads/audio/unique.wav', 'now')
            """,
            (person_id,),
        )
        connection.commit()
    with pytest.raises(RuntimeError, match="rebuild refused"):
        build_database(built_database)


def test_expected_counts_and_idempotency(built_database: Path) -> None:
    first_counts = build_database(built_database)
    second_counts = build_database(built_database)
    assert first_counts == second_counts
    assert second_counts["source_records"] == 105
    assert second_counts["canonical_persons"] == 53
    assert second_counts["linked_source_records"] == 84
    assert second_counts["unresolved_source_records"] == 21


def find_source(connection, filename: str, row: int):
    return connection.execute(
        "SELECT * FROM source_records WHERE source_filename = ? AND source_row_number = ?",
        (filename, row),
    ).fetchone()


def test_high_confidence_records_share_person(built_database: Path) -> None:
    with open_database(built_database) as connection:
        source_1 = find_source(connection, "source1_naukri_applicants.csv", 2)
        source_2 = find_source(connection, "source2_gig_workers.csv", 11)
        source_3 = find_source(connection, "source3_cbnexus_contacts.csv", 22)
    assert source_1["person_id"] == source_2["person_id"] == source_3["person_id"]


def test_distinct_people_do_not_collapse(built_database: Path) -> None:
    with open_database(built_database) as connection:
        arjun_mehta = find_source(connection, "source1_naukri_applicants.csv", 20)
        arjun_mishra = find_source(connection, "source1_naukri_applicants.csv", 17)
    assert arjun_mehta["person_id"] != arjun_mishra["person_id"]


def test_arjun_mehta_ambiguity_is_unresolved(built_database: Path) -> None:
    with open_database(built_database) as connection:
        rows = [
            find_source(connection, "source2_gig_workers.csv", 18),
            find_source(connection, "source3_cbnexus_contacts.csv", 5),
            find_source(connection, "source3_cbnexus_contacts.csv", 28),
        ]
    assert all(row["match_status"] == "AMBIGUOUS_REVIEW" for row in rows)
    assert all(row["person_id"] is None for row in rows)


def test_deepak_nair_ambiguity_is_unresolved(built_database: Path) -> None:
    with open_database(built_database) as connection:
        ambiguous = find_source(connection, "source2_gig_workers.csv", 32)
        linked = find_source(connection, "source2_gig_workers.csv", 15)
    assert ambiguous["match_status"] == "AMBIGUOUS_REVIEW"
    assert ambiguous["person_id"] is None
    assert linked["match_status"] == "MATCHED_HIGH_CONFIDENCE"
    assert linked["person_id"] is not None


@pytest.mark.parametrize(
    ("filename", "row"),
    [
        ("source2_gig_workers.csv", 12),
        ("source2_gig_workers.csv", 20),
        ("source3_cbnexus_contacts.csv", 16),
    ],
)
def test_known_invalid_rows_are_preserved(built_database: Path, filename: str, row: int) -> None:
    with open_database(built_database) as connection:
        source_record = find_source(connection, filename, row)
    assert source_record["match_status"] == "INVALID_SOURCE_RECORD"
    assert source_record["person_id"] is None
    assert json.loads(source_record["raw_record_json"]) is not None


def test_raw_json_preserves_source_data(built_database: Path) -> None:
    with open_database(built_database) as connection:
        row = find_source(connection, "source1_naukri_applicants.csv", 2)
    raw = json.loads(row["raw_record_json"])
    assert raw["Full Name"] == "Tanvi Gupta"
    assert raw["Phone"] == "+919000000254"
    assert raw["Current CTC"] == "417964"


def test_foreign_key_integrity_is_enforced(built_database: Path) -> None:
    with open_database(built_database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO source_records (
                    source_system, source_filename, source_row_number, person_id,
                    match_status, match_confidence, match_evidence_json,
                    match_reason, candidate_entity_ids_json,
                    conflicting_evidence_json, raw_record_json, created_at
                ) VALUES ('test', 'test.csv', 1, 999999, 'NEW_ENTITY', 'NEW',
                          '[]', 'test', '[]', '{}', '{}', 'now')
                """
            )


def test_summary_status_counts(built_database: Path) -> None:
    with open_database(built_database) as connection:
        counts = summary_counts(connection)
    assert counts["MATCHED_HIGH_CONFIDENCE"] == 31
    assert counts["AMBIGUOUS_REVIEW"] == 18
    assert counts["INVALID_SOURCE_RECORD"] == 3
