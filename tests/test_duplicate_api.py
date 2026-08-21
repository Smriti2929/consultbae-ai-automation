from pathlib import Path

import pytest

from src.app.app import create_app
from src.database.db import initialize_schema, open_database


@pytest.fixture()
def duplicate_api(tmp_path: Path):
    database_path = tmp_path / "duplicate-api.db"
    with open_database(database_path) as connection:
        initialize_schema(connection)
        connection.executemany(
            """
            INSERT INTO persons (
                provisional_entity_id, canonical_name, canonical_email,
                canonical_phone, canonical_conflicts_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, '{}', 'now', 'now')
            """,
            [
                ("ENTITY-TANVI", "Tanvi Gupta", "tanvi.gupta31@example.com", "9000000254"),
                ("ENTITY-OTHER", "Other Person", "other@example.com", "9111111111"),
            ],
        )
        connection.commit()
    app = create_app(
        {"TESTING": True, "DATABASE": database_path, "UPLOAD_DIRECTORY": tmp_path / "uploads"}
    )
    return app.test_client(), database_path


def test_known_email_duplicate(duplicate_api) -> None:
    client, _ = duplicate_api
    response = client.post("/api/check-duplicate", json={"email": " Tanvi.Gupta31@Example.COM "})
    assert response.status_code == 200
    assert response.get_json() == {
        "duplicate": True, "status": "MATCHED_HIGH_CONFIDENCE", "person_id": 1,
        "matched_by": ["email"], "canonical_name": "Tanvi Gupta",
    }


def test_known_phone_duplicate(duplicate_api) -> None:
    client, _ = duplicate_api
    response = client.post("/api/check-duplicate", json={"phone": "+91 90000-00254"})
    assert response.status_code == 200
    assert response.get_json()["matched_by"] == ["phone"]
    assert response.get_json()["duplicate"] is True


def test_both_identifiers_match_same_person(duplicate_api) -> None:
    client, _ = duplicate_api
    response = client.post(
        "/api/check-duplicate",
        json={"email": "tanvi.gupta31@example.com", "phone": "9000000254"},
    )
    assert response.status_code == 200
    assert response.get_json()["matched_by"] == ["phone", "email"]
    assert response.get_json()["person_id"] == 1


def test_unknown_person_returns_not_duplicate_without_writes(duplicate_api) -> None:
    client, database_path = duplicate_api
    response = client.post(
        "/api/check-duplicate",
        json={"email": "unknown@example.com", "phone": "9222222222"},
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "duplicate": False, "status": "NO_MATCH", "person_id": None, "matched_by": [],
    }
    with open_database(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM persons").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM source_records").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM audio_submissions").fetchone()[0] == 0


def test_name_only_does_not_match(duplicate_api) -> None:
    client, _ = duplicate_api
    response = client.post("/api/check-duplicate", json={"name": "Tanvi Gupta"})
    assert response.status_code == 400
    assert response.get_json()["status"] == "INVALID_REQUEST"
    assert response.get_json()["duplicate"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email"},
        {"phone": "123"},
        {"email": "invalid", "phone": "also-invalid"},
    ],
)
def test_invalid_identifiers_are_rejected(duplicate_api, payload) -> None:
    client, _ = duplicate_api
    response = client.post("/api/check-duplicate", json=payload)
    assert response.status_code == 400
    assert response.get_json()["status"] == "INVALID_REQUEST"


def test_conflicting_strong_identifiers(duplicate_api) -> None:
    client, _ = duplicate_api
    response = client.post(
        "/api/check-duplicate",
        json={"email": "tanvi.gupta31@example.com", "phone": "9111111111"},
    )
    assert response.status_code == 409
    assert response.get_json() == {
        "duplicate": False,
        "status": "AMBIGUOUS_REVIEW",
        "person_id": None,
        "matched_by": [],
        "reason": "Email and phone resolve to different canonical people.",
    }


def test_malformed_json(duplicate_api) -> None:
    client, _ = duplicate_api
    response = client.post(
        "/api/check-duplicate", data='{"email":', content_type="application/json"
    )
    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["status"] == "INVALID_REQUEST"
