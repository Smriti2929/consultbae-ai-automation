"""Small Flask application for collecting worker audio submissions."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Flask, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from src.audio.metadata import AudioMetadataError, extract_audio_metadata
from src.database.db import DEFAULT_DATABASE_PATH, ensure_application_schema, open_database
from src.matching.normalization import normalize_name, normalize_phone


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UPLOAD_DIRECTORY = PROJECT_ROOT / "uploads" / "audio"
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".webm"}


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=DEFAULT_DATABASE_PATH,
        UPLOAD_DIRECTORY=DEFAULT_UPLOAD_DIRECTORY,
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,
        ALLOWED_AUDIO_EXTENSIONS=ALLOWED_AUDIO_EXTENSIONS,
        METADATA_EXTRACTOR=extract_audio_metadata,
    )
    if test_config:
        app.config.update(test_config)

    database_path = Path(app.config["DATABASE"])
    upload_directory = Path(app.config["UPLOAD_DIRECTORY"])
    upload_directory.mkdir(parents=True, exist_ok=True)
    connection = open_database(database_path)
    try:
        ensure_application_schema(connection)
    finally:
        connection.close()

    @app.errorhandler(RequestEntityTooLarge)
    def file_too_large(_error):
        return render_template("index.html", error="Audio file is too large (maximum 25 MB)."), 413

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/")
    def submit_audio():
        submitted_name = request.form.get("name", "")
        submitted_phone = request.form.get("phone", "")
        if not submitted_name.strip():
            return render_template("index.html", error="Name is required."), 400
        if not submitted_phone.strip():
            return render_template("index.html", error="Phone number is required."), 400

        normalized_phone = normalize_phone(submitted_phone)
        if normalized_phone is None:
            return render_template(
                "index.html", error="Enter a valid 10-digit phone number."
            ), 400
        normalized_name = normalize_name(submitted_name)

        audio = request.files.get("audio")
        if audio is None or not audio.filename:
            return render_template("index.html", error="Choose an audio file."), 400
        safe_original = secure_filename(audio.filename)
        if not safe_original:
            return render_template("index.html", error="The audio filename is invalid."), 400
        extension = Path(safe_original).suffix.lower()
        if extension not in app.config["ALLOWED_AUDIO_EXTENSIONS"]:
            return render_template(
                "index.html", error="Unsupported audio type. Use WAV, MP3, M4A, OGG, or WebM."
            ), 400

        connection = open_database(database_path)
        stored_path: Path | None = None
        try:
            matches = connection.execute(
                "SELECT id FROM persons WHERE canonical_phone = ?", (normalized_phone,)
            ).fetchall()
            if len(matches) > 1:
                return render_template(
                    "index.html",
                    error="This phone matches multiple people and requires manual review.",
                ), 409

            stored_filename = f"{uuid4().hex}{extension}"
            stored_path = upload_directory / stored_filename
            audio.save(stored_path)
            metadata = app.config["METADATA_EXTRACTOR"](stored_path)
            timestamp = datetime.now(timezone.utc).isoformat()

            with connection:
                if matches:
                    person_id = matches[0]["id"]
                    person_result = "linked to an existing worker"
                else:
                    cursor = connection.execute(
                        """
                        INSERT INTO persons (
                            provisional_entity_id, canonical_name, canonical_phone,
                            canonical_conflicts_json, created_at, updated_at
                        ) VALUES (?, ?, ?, '{}', ?, ?)
                        """,
                        (
                            f"audio:{uuid4().hex}", submitted_name.strip(),
                            normalized_phone, timestamp, timestamp,
                        ),
                    )
                    person_id = cursor.lastrowid
                    person_result = "created as a new worker"

                cursor = connection.execute(
                    """
                    INSERT INTO audio_submissions (
                        person_id, submitted_name, submitted_phone, normalized_name,
                        normalized_phone, original_filename, stored_filename,
                        file_path, duration_seconds, sample_rate_hz, bitrate_bps,
                        loudness_db, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        person_id, submitted_name, submitted_phone, normalized_name,
                        normalized_phone, audio.filename, stored_filename,
                        str(Path("uploads") / "audio" / stored_filename),
                        metadata.duration_seconds, metadata.sample_rate_hz,
                        metadata.bitrate_bps, metadata.loudness_db, timestamp,
                    ),
                )
            return render_template(
                "index.html",
                success=f"Audio submitted successfully (submission #{cursor.lastrowid}); {person_result}.",
            ), 201
        except AudioMetadataError as error:
            if stored_path is not None:
                stored_path.unlink(missing_ok=True)
            return render_template(
                "index.html", error=f"Audio analysis failed: {error}"
            ), 400
        except (OSError, sqlite3.Error):
            if stored_path is not None:
                stored_path.unlink(missing_ok=True)
            app.logger.exception("Audio submission failed")
            return render_template(
                "index.html", error="The submission could not be saved. Please try again."
            ), 500
        finally:
            connection.close()

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
