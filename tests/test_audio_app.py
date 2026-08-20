import io
import sqlite3
from pathlib import Path

import pytest

from src.audio.metadata import AudioMetadata, AudioMetadataError
from src.app.app import create_app
from src.database.db import initialize_schema, open_database


TEST_METADATA = AudioMetadata(1.25, 16000, 256000, -18.4)


def successful_metadata(_path: Path) -> AudioMetadata:
    return TEST_METADATA


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
            "METADATA_EXTRACTOR": successful_metadata,
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


def test_upload_below_25_mb_is_not_size_rejected(app_environment) -> None:
    app, database_path, upload_path = app_environment
    assert app.config["MAX_CONTENT_LENGTH"] == 25 * 1024 * 1024
    data = {
        "name": "Known Worker",
        "phone": "9000000254",
        "audio": (io.BytesIO(b"a" * 1024), "small.wav"),
    }
    response = app.test_client().post("/", data=data, content_type="multipart/form-data")
    assert response.status_code == 201
    assert counts(database_path) == (1, 1)
    assert len(list(upload_path.iterdir())) == 1


def test_oversized_upload_returns_friendly_413_without_artifacts(app_environment) -> None:
    app, database_path, upload_path = app_environment
    data = {
        "name": "Oversized New Worker",
        "phone": "9876543210",
        "audio": (io.BytesIO(b"a" * (25 * 1024 * 1024 + 1)), "large.wav"),
    }
    response = app.test_client().post("/", data=data, content_type="multipart/form-data")
    assert response.status_code == 413
    assert b"25 MB" in response.data
    assert b"Audio file is too large" in response.data
    assert b"Traceback" not in response.data
    assert b"RequestEntityTooLarge" not in response.data
    assert b"werkzeug.exceptions" not in response.data
    assert counts(database_path) == (1, 0)
    assert not list(upload_path.iterdir())


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
        assert row["duration_seconds"] == TEST_METADATA.duration_seconds
        assert row["sample_rate_hz"] == TEST_METADATA.sample_rate_hz
        assert row["bitrate_bps"] == TEST_METADATA.bitrate_bps
        assert row["loudness_db"] == TEST_METADATA.loudness_db
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


def test_metadata_failure_removes_file_and_leaves_existing_person(app_environment) -> None:
    app, database_path, upload_path = app_environment

    def fail(_path: Path):
        raise AudioMetadataError("not readable audio")

    app.config["METADATA_EXTRACTOR"] = fail
    response = submit(app.test_client())
    assert response.status_code == 400
    assert b"Audio analysis failed" in response.data
    assert counts(database_path) == (1, 0)
    assert not list(upload_path.iterdir())


def test_metadata_failure_does_not_leave_new_person(app_environment) -> None:
    app, database_path, upload_path = app_environment

    def fail(_path: Path):
        raise AudioMetadataError("not readable audio")

    app.config["METADATA_EXTRACTOR"] = fail
    response = submit(app.test_client(), name="New Worker", phone="9876543210")
    assert response.status_code == 400
    assert counts(database_path) == (1, 0)
    assert not list(upload_path.iterdir())


def stored_filename(database_path: Path) -> str:
    with open_database(database_path) as connection:
        return connection.execute(
            "SELECT stored_filename FROM audio_submissions ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]


def test_submissions_empty_state(app_environment) -> None:
    app, _, _ = app_environment
    response = app.test_client().get("/submissions")
    assert response.status_code == 200
    assert b"No audio submissions yet" in response.data
    assert b"Submit new audio" in response.data


def test_submission_dashboard_formats_metadata_and_identity(app_environment) -> None:
    app, _, _ = app_environment
    client = app.test_client()
    assert submit(client, name="Worker-entered Name").status_code == 201
    response = client.get("/submissions")
    assert response.status_code == 200
    assert b"Worker-entered Name" in response.data
    assert b"Canonical: Known Worker" in response.data
    assert b"1.25 s" in response.data
    assert b"16 kHz" in response.data
    assert b"256 kbps" in response.data
    assert b"-18.4 dB" in response.data
    assert b"LUFS" not in response.data
    assert b"<audio controls" in response.data


def test_audio_endpoint_serves_file_and_blocks_traversal(app_environment) -> None:
    app, database_path, upload_path = app_environment
    client = app.test_client()
    assert submit(client).status_code == 201
    filename = stored_filename(database_path)
    response = client.get(f"/audio/{filename}")
    assert response.status_code == 200
    assert response.data == b"test audio"
    secret = upload_path.parent / "secret.txt"
    secret.write_bytes(b"outside secret")
    traversal = client.get("/audio/..%2Fsecret.txt")
    assert traversal.status_code == 404
    assert b"outside secret" not in traversal.data


def test_missing_audio_file_is_unavailable_and_endpoint_404(app_environment) -> None:
    app, database_path, upload_path = app_environment
    client = app.test_client()
    assert submit(client).status_code == 201
    filename = stored_filename(database_path)
    (upload_path / filename).unlink()
    dashboard = client.get("/submissions")
    assert dashboard.status_code == 200
    assert b"Audio unavailable" in dashboard.data
    assert client.get(f"/audio/{filename}").status_code == 404


def test_legacy_null_metadata_does_not_crash_dashboard(app_environment) -> None:
    app, database_path, _ = app_environment
    client = app.test_client()
    assert submit(client).status_code == 201
    with open_database(database_path) as connection:
        connection.execute(
            """UPDATE audio_submissions
               SET duration_seconds = NULL, sample_rate_hz = NULL,
                   bitrate_bps = NULL, loudness_db = NULL"""
        )
        connection.commit()
    response = client.get("/submissions")
    assert response.status_code == 200
    assert response.data.count("—".encode("utf-8")) >= 4


def test_submissions_are_newest_first(app_environment) -> None:
    app, database_path, _ = app_environment
    client = app.test_client()
    assert submit(client, name="Older Worker").status_code == 201
    assert submit(client, name="Newer Worker").status_code == 201
    with open_database(database_path) as connection:
        rows = connection.execute("SELECT id FROM audio_submissions ORDER BY id").fetchall()
        connection.execute(
            "UPDATE audio_submissions SET created_at = '2026-01-01T00:00:00+00:00' WHERE id = ?",
            (rows[0]["id"],),
        )
        connection.execute(
            "UPDATE audio_submissions SET created_at = '2026-02-01T00:00:00+00:00' WHERE id = ?",
            (rows[1]["id"],),
        )
        connection.commit()
    response = client.get("/submissions")
    assert response.data.index(b"Newer Worker") < response.data.index(b"Older Worker")
