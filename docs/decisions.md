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

## Phase 2

### Decision: preserve raw values and normalize only comparison fields

Names are safely converted to text, trimmed, internal whitespace is collapsed,
and case is lowered. Emails are trimmed, lowercased, and accepted only when they
pass a basic structural check. Cities receive spacing/case normalization for
supporting evidence. Phone punctuation is removed, and a leading `+91` or `91`
is removed only when exactly 10 digits remain.

**Why:** Phase 1 found case, whitespace, and Indian country-code presentation
differences. Retaining both raw and normalized values makes every comparison
auditable.

**Alternatives considered:** overwriting source values or saving cleaned copies.

**Why rejected/deferred:** raw evidence must remain immutable, and Phase 2 does
not need a persisted normalized dataset or database.

### Decision: valid exact email and phone are strong identifiers

A record is `MATCHED_HIGH_CONFIDENCE` only when its exact valid normalized email
or phone points to one existing provisional entity. When both point to the same
entity, both are recorded as evidence.

**Why:** Phase 1 found 15 exact normalized email overlaps and 15 exact normalized
phone overlaps, with no differing normalized names in those pairs.

**Alternatives considered:** exact name matching and fuzzy name matching.

**Why rejected/deferred:** names are not unique, and Phase 1 exposed one-to-many
cases. Fuzzy matching would introduce thresholds and false-positive risk without
being required by the assignment.

### Decision: exact name and normalized city are supporting evidence only

Name equality never attaches a record to an entity. It produces
`AMBIGUOUS_REVIEW` when existing candidate entities share the name. City is
retained in the audit output but is never indexed as an identifier.

**Why:** `Arjun Mehta` and `Deepak Nair` demonstrate that one name can refer to
multiple source records with conflicting strong values. Cities are broadly
shared and have known spelling variants.

**Alternatives considered:** merge when name and city agree.

**Why rejected/deferred:** that combination is still not unique and would make
an unsupported identity claim.

### Decision: conflicting strong identifiers require review

If email points to one entity and phone points to another, the record is
`AMBIGUOUS_REVIEW`. Both candidate IDs and the field-to-entity conflict are
recorded; neither identifier wins silently.

**Why:** conflict-safe behavior is necessary even though the current raw files
do not contain this pattern.

**Alternative considered:** give email or phone fixed precedence.

**Why rejected:** the data provides no basis for assuming one is always more
reliable, and a precedence rule could merge two people.

### Decision: do not remove a leading trunk-prefix zero

An 11-digit phone such as `09000000131` remains invalid as a strong normalized
phone in Phase 2.

**Why:** removing the zero was explicitly outside the approved normalization
scope, and Phase 1 treated these as manual-review candidates.

**Alternative considered:** remove a leading `0` when 10 digits remain.

**Why rejected/deferred:** it may be plausible for this dataset, but it expands
the matching rule and should be approved and tested separately.

### Decision: retain invalid source records in the audit

The empty Source 2 row, shifted Source 2 row, and embedded Source 3 header receive
`INVALID_SOURCE_RECORD` with an explanation. They are not repaired or deleted.

**Why:** their declared fields cannot provide reliable identity evidence, while
retaining them preserves a complete accounting of all source rows.

**Alternative considered:** repair the visibly shifted row automatically.

**Why rejected:** the apparent intended alignment is an inference and silently
changing it would make the audit less defensible.

### Decision: generate provisional entities, not a canonical database

Records are processed in source order and assigned transparent IDs such as
`ENTITY-0001`. These IDs exist only in the audit run. They are not final database
keys or canonical-person claims.

**Why:** provisional IDs make match explanations readable while respecting the
Phase 2 stop boundary.

## Phase 3

### Database choice: SQLite with Python's built-in driver

The canonical assignment database is `data/processed/consultbae.db`, accessed
with Python's built-in `sqlite3` module. Foreign-key enforcement is enabled on
every connection.

**Why:** SQLite is portable, requires no service or credentials, and is enough
for 105 source records. The built-in driver keeps the database layer small and
easy to explain.

**Alternative considered:** SQLAlchemy or a server database.

**Why rejected:** neither reduces complexity for this two-table assignment, and
PostgreSQL/MySQL would add unnecessary infrastructure.

### Schema design: canonical persons separated from source records

`persons` contains one row per safely created entity. `source_records` contains
one row per original CSV row and has a nullable foreign key to `persons`.
Status, confidence, evidence, reason, candidate IDs, normalized identity fields,
and the full raw row JSON are stored with each source record.

**Why:** canonical fields are convenient to query, while separate source rows
preserve provenance and prevent source-specific attributes from being lost.
The nullable foreign key lets ambiguous and invalid rows remain represented
without claiming a person assignment.

**Alternative considered:** one wide merged table.

**Why rejected:** it would mix incompatible source schemas, obscure provenance,
and encourage ambiguous records to be forced into canonical rows.

### Provisional-to-persistent entity mapping

Phase 2 creates 53 provisional entities. Inspection confirmed that only
`NEW_ENTITY` and `MATCHED_HIGH_CONFIDENCE` records are attached to them; all
ambiguous decisions have no matched provisional entity. Each safe provisional
entity therefore creates one `persons` row. SQLite assigns the integer `id`,
while unique `provisional_entity_id` records the reproducible mapping.

**Why:** this preserves Phase 2 semantics without treating a temporary ID as the
database primary key. Ambiguous and invalid source records keep `person_id NULL`.

### Canonical-field precedence

Only safely attached source records are considered. Records are ordered by
source priority—Source 1, Source 2, Source 3—and then CSV row number. The first
present whitespace-trimmed raw name becomes `canonical_name`; the first present
valid normalized email, phone, and city become their canonical fields.

All additional distinct normalized identity values remain in linked source rows.
When an entity contains more than one name, email, phone, or city,
`canonical_conflicts_json` records every competing value.

**Why:** this is deterministic, does not depend on whichever record was processed
last, and does not invent missing values. Source 1 has the broadest identity
coverage, making it a reasonable representative source for this assignment.

**Alternatives considered:** last-value wins, longest string wins, majority vote,
or normalizing business fields such as CTC and rate.

**Why rejected/deferred:** those policies can conceal disagreement or introduce
unsupported semantic conversions. CTC scale, rate units, date formats, status,
and verification values remain exactly available in `raw_record_json`.

### Provenance and unresolved records

The unique pair `(source_filename, source_row_number)` identifies a source row.
Its complete original column/value mapping is stored in `raw_record_json`.
Eighteen ambiguous rows and three invalid rows are inserted with no person ID;
none is discarded or silently repaired.

**Why:** every one of the 105 rows remains traceable, including the empty row,
shifted Isha Chopra row, and embedded header.

### Idempotency: validated atomic rebuild

Each ingestion run builds the complete schema and data in
`consultbae.db.building`, validates counts and foreign keys, closes it, and then
atomically replaces `consultbae.db`. It does not append to an existing database.

**Why:** a deterministic rebuild is the simplest idempotent strategy for a small
take-home dataset. Validation occurs before the previous usable database is
replaced, preventing duplicates and avoiding a partially built final file.

**Alternative considered:** row-by-row upserts.

**Why rejected:** upserts add conflict/update behavior that is unnecessary while
the assignment database is fully reproducible from immutable CSV files.
