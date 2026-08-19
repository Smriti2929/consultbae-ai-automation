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
