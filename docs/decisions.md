# Decisions

## Phase 1

- Treat every file in `data/raw/` as immutable source evidence.
- Inspect all CSV files automatically instead of hard-coding filenames.
- Detect identity-related columns from broad column-name terms rather than a
  fixed schema.
- Report suspicious patterns without cleaning values or assigning matches.
- Keep checks transparent and rule-based so each result is interview-defensible.
- Store only a generated inspection summary in `data/processed/`.
- Defer normalization, entity resolution, database design, Flask, n8n, and audio
  processing to later phases.
