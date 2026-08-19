# ConsultBae AI Automation

This repository contains work for a 48-hour AI automation take-home assignment.
Only Phase 1 is currently implemented: repository scaffolding and read-only
inspection of the messy source CSV files.

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

## Current scope

Phase 1 intentionally excludes entity matching, canonical database creation,
Flask, n8n workflows, and audio processing.
