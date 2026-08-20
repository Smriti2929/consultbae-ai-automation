import io
import sqlite3
from pathlib import Path

import pytest

from src.app.app import create_app
from src.database.db import initialize_schema, open_database


@pytest.fixture()
def app_environment(tmp_path: Path):
    database_path = tmp_path / "app.db"
    upload_path = tmp_path / "uploads"
    with open_database(database_path) as connection:
        initialize_schema(connection)
        connection.execute(
            """
            INSERT INTO persons (
                provisional_entity_id, canonical_name, canonical_phone,
                canonical_conflicts_json, created_at, updated_at
            ) VALUES ('ENTITY-TEST', 'Known Worker', '9000000254', '{}', 'now', 'now')
            """
        )
        connection.commit()
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": database_path,
            "UPLOAD_DIRECTORY": upload_path,
        }
    )
    return app, database_path, upload_path


def submit(client, name="Known Worker", phone="9000000254", filename="audio.wav"):
    data = {"name": name, "phone": phone}
    if filename is not None:
        data["audio"] = (io.BytesIO(b"test audio"), filename)
    return client.post("/", data=data, content_type="multipart/form-data")


def counts(database_path: Path):
    with open_database(database_path) as connection:
        return (
            connection.execute("SELECT COUNT(*) FROM persons").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM audio_submissions").fetchone()[0],
        )


def test_home_page_loads(app_environment) -> None:
    app, _, _ = app_environment
    response = app.test_client().get("/")
    assert response.status_code == 200
    assert b"Submit your audio" in response.data


def test_existing_person_submission_is_linked_without_duplication(app_environment) -> None:
    app, database_path, upload_path = app_environment
    response = submit(app.test_client())
    assert response.status_code == 201
    assert b"linked to an existing worker" in response.data
    assert counts(database_path) == (1, 1)
    assert len(list(upload_path.iterdir())) == 1
    with open_database(database_path) as connection:
        row = connection.execute("SELECT * FROM audio_submissions").fetchone()
        person = connection.execute("SELECT * FROM persons").fetchone()
        assert row["person_id"] == person["id"]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_unseen_phone_creates_person_and_submission(app_environment) -> None:
    app, database_path, _ = app_environment
    response = submit(app.test_client(), name="New Worker", phone="+91 98765-43210")
    assert response.status_code == 201
    assert b"created as a new worker" in response.data
    assert counts(database_path) == (2, 1)
    with open_database(database_path) as connection:
        person = connection.execute(
            "SELECT * FROM persons WHERE canonical_phone = '9876543210'"
        ).fetchone()
        submission = connection.execute("SELECT * FROM audio_submissions").fetchone()
        assert person is not None
        assert submission["person_id"] == person["id"]
        assert submission["submitted_phone"] == "+91 98765-43210"


def test_same_original_filename_does_not_overwrite(app_environment) -> None:
    app, database_path, upload_path = app_environment
    client = app.test_client()
    assert submit(client).status_code == 201
    assert submit(client).status_code == 201
    with open_database(database_path) as connection:
        names = [row[0] for row in connection.execute("SELECT stored_filename FROM audio_submissions")]
    assert len(names) == len(set(names)) == 2
    assert len(list(upload_path.iterdir())) == 2


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"phone": "123"}, b"valid 10-digit phone"),
        ({"filename": None}, b"Choose an audio file"),
        ({"filename": "audio.txt"}, b"Unsupported audio type"),
        ({"name": ""}, b"Name is required"),
        ({"phone": ""}, b"Phone number is required"),
    ],
)
def test_validation_errors_do_not_write(app_environment, overrides, message) -> None:
    app, database_path, upload_path = app_environment
    response = submit(app.test_client(), **overrides)
    assert response.status_code == 400
    assert message in response.data
    assert counts(database_path) == (1, 0)
    assert not list(upload_path.iterdir())


def test_ambiguous_phone_requires_manual_review(app_environment) -> None:
    app, database_path, upload_path = app_environment
    with open_database(database_path) as connection:
        connection.execute(
            """
            INSERT INTO persons (
                provisional_entity_id, canonical_name, canonical_phone,
                canonical_conflicts_json, created_at, updated_at
            ) VALUES ('ENTITY-DUPLICATE', 'Other Worker', '9000000254', '{}', 'now', 'now')
            """
        )
        connection.commit()
    response = submit(app.test_client())
    assert response.status_code == 409
    assert b"multiple people" in response.data
    assert counts(database_path) == (2, 0)
    assert not list(upload_path.iterdir())
