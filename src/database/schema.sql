PRAGMA foreign_keys = ON;

CREATE TABLE persons (
    id INTEGER PRIMARY KEY,
    provisional_entity_id TEXT NOT NULL UNIQUE,
    canonical_name TEXT,
    canonical_email TEXT,
    canonical_phone TEXT,
    canonical_city TEXT,
    canonical_conflicts_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE source_records (
    id INTEGER PRIMARY KEY,
    source_system TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    person_id INTEGER,
    match_status TEXT NOT NULL CHECK (match_status IN (
        'MATCHED_HIGH_CONFIDENCE',
        'NEW_ENTITY',
        'AMBIGUOUS_REVIEW',
        'INVALID_SOURCE_RECORD'
    )),
    match_confidence TEXT NOT NULL CHECK (match_confidence IN (
        'HIGH', 'NEW', 'REVIEW_REQUIRED', 'INVALID'
    )),
    match_evidence_json TEXT NOT NULL,
    match_reason TEXT NOT NULL,
    candidate_entity_ids_json TEXT NOT NULL,
    conflicting_evidence_json TEXT NOT NULL,
    raw_name TEXT,
    raw_email TEXT,
    raw_phone TEXT,
    raw_city TEXT,
    normalized_name TEXT,
    normalized_email TEXT,
    normalized_phone TEXT,
    normalized_city TEXT,
    raw_record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (source_filename, source_row_number),
    FOREIGN KEY (person_id) REFERENCES persons(id)
);

CREATE INDEX idx_source_records_person_id ON source_records(person_id);
CREATE INDEX idx_source_records_status ON source_records(match_status);

CREATE TABLE audio_submissions (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL,
    submitted_name TEXT NOT NULL,
    submitted_phone TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    normalized_phone TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (person_id) REFERENCES persons(id)
);

CREATE INDEX idx_audio_submissions_person_id ON audio_submissions(person_id);
