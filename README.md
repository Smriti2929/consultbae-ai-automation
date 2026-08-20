# ConsultBae AI Automation

This repository contains work for a 48-hour AI automation take-home assignment.
It currently includes raw-data inspection, deterministic entity resolution,
and an auditable canonical SQLite ingestion pipeline.

## Phase 1: inspect the raw data

1. Create and activate a Python virtual environment.
2. Install the dependency:

   ```bash
   pip install -r requirements.txt
   ```

3. Place source CSV files in `data/raw/`.
4. From the repository root, run:

   ```bash
   python -m src.ingestion.inspect_data
   ```

The command prints a readable profile for every CSV and writes a simple JSON
summary to `data/processed/inspection_summary.json`. It does not clean, match,
delete, or modify source records. Files in `data/raw/` are treated as immutable.

For the targeted Phase 1 investigation of suspicious records and exact
cross-source comparison values, run:

```bash
python -m src.ingestion.investigate_records
```

This second command creates trimmed comparison forms in memory only and prints
the original source values for manual review. It does not save normalized data
or make entity-matching decisions.

## Phase 2: normalization and matching audit

Generate deterministic, explainable matching decisions without creating a
database:

```bash
python -m src.matching.generate_report
```

The command writes `data/processed/matching_audit.json` and
`data/processed/matching_audit.csv`. Each row preserves the original identity
values, shows temporary normalized values, and explains its status. Run the
focused tests with `python -m pytest`.

## Phase 3: build and inspect SQLite

Rebuild the canonical database deterministically:

```bash
python -m src.database.ingest
```

The database is written to `data/processed/consultbae.db`. A successful build is
expected to report 105 source records, 53 canonical persons, 84 linked source
records, and 21 unresolved records (18 ambiguous plus 3 invalid).

Inspect counts, sample persons, linked provenance, and unresolved rows with:

```bash
python -m src.database.inspect_db
```

Repeated ingestion rebuilds and atomically replaces the assignment database;
it does not append duplicate records. Once worker audio submissions exist,
ingestion refuses to replace the database so application data is not silently
lost. Back up or deliberately migrate that data before rebuilding.

## Phase 4A: run the audio app

Install dependencies and ensure the Phase 3 database exists, then run:

```bash
pip install -r requirements.txt
python -m src.database.ingest
python -m src.app.app
```

Visit `http://127.0.0.1:5000`. Alternatively, use:

```bash
flask --app src.app.app run
```

The worker enters a name and valid phone number and uploads WAV, MP3, M4A, OGG,
or WebM audio (maximum 25 MB). The app normalizes the phone with the Phase 2
rule. One canonical phone match links the submission to that person; no match
creates a person containing only the submitted name and normalized phone;
multiple matches require manual review. Audio is stored under `uploads/audio/`,
while its submission and person relationship are stored in SQLite.

### Audio-analysis prerequisites

Phase 4B requires both FFmpeg and FFprobe to be installed and available on
`PATH`. Verify the installation before launching the app:

```bash
ffmpeg -version
ffprobe -version
```

On Windows, install an FFmpeg distribution with a package manager or from the
official FFmpeg download links, then open a new terminal so the updated `PATH`
is visible.

Every accepted upload stores duration in seconds, sample rate in Hz, bitrate in
bits per second, and loudness in dB. FFprobe supplies the first three values.
Stream bitrate is preferred, with container bitrate as a deterministic fallback.
FFmpeg's `volumedetect` filter supplies `mean_volume`; `loudness_db` is therefore
mean volume in dBFS-style decibels, not LUFS.

A supported filename extension is only an initial check. If FFprobe cannot find
a readable audio stream, any required value is unavailable, or FFmpeg cannot
analyze loudness, the request is rejected. The temporary uploaded file is
removed and no person or submission created by that request is committed.

Run all automated tests with:

```bash
python -m pytest
```

## Current scope

The current implementation intentionally excludes audio quality/noise scoring,
browser recording, n8n workflows, deployment, authentication, playback, and
dashboard integration.
