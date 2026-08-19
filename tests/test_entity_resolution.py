from src.matching.entity_resolution import (
    AMBIGUOUS_REVIEW,
    INVALID_SOURCE_RECORD,
    MATCHED_HIGH_CONFIDENCE,
    NEW_ENTITY,
    EntityMatcher,
    SourceRecord,
)
from src.matching.generate_report import SOURCE_CONFIGS, records_from_source


def record(row: int, name: str, email: str | None = None, phone: str | None = None) -> SourceRecord:
    from src.matching.normalization import normalize_email, normalize_name, normalize_phone

    return SourceRecord(
        source_system="test",
        source_file="test.csv",
        source_row=row,
        raw_name=name,
        raw_email=email,
        raw_phone=phone,
        normalized_name=normalize_name(name),
        normalized_email=normalize_email(email),
        normalized_phone=normalize_phone(phone),
    )


def test_exact_email_is_high_confidence() -> None:
    matcher = EntityMatcher()
    first = matcher.process(record(2, "Person One", "person@example.com"))
    second = matcher.process(record(3, "Person One", " PERSON@EXAMPLE.COM "))
    assert first.status == NEW_ENTITY
    assert second.status == MATCHED_HIGH_CONFIDENCE
    assert second.evidence == ["normalized_email"]


def test_exact_phone_is_high_confidence() -> None:
    matcher = EntityMatcher()
    matcher.process(record(2, "Person One", phone="9000000131"))
    decision = matcher.process(record(3, "Person One", phone="+91-9000000131"))
    assert decision.status == MATCHED_HIGH_CONFIDENCE
    assert decision.evidence == ["normalized_phone"]


def test_name_only_does_not_merge() -> None:
    matcher = EntityMatcher()
    matcher.process(record(2, "Same Name", "first@example.com"))
    decision = matcher.process(record(3, "Same Name", "second@example.com"))
    assert decision.status == AMBIGUOUS_REVIEW
    assert decision.matched_entity_id is None


def test_one_to_many_name_is_ambiguous() -> None:
    matcher = EntityMatcher()
    first = matcher.process(record(2, "Shared Name", "one@example.com"))
    second = matcher.process(record(3, "Different Name", "two@example.com"))
    # A strong email match can add a second observed name to an entity. This
    # creates two real candidates for a later name-only record.
    matcher.process(record(4, "Shared Name", "two@example.com"))
    decision = matcher.process(record(5, "Shared Name"))
    assert first.matched_entity_id != second.matched_entity_id
    assert decision.status == AMBIGUOUS_REVIEW
    assert len(decision.candidate_entity_ids) == 2


def test_conflicting_strong_identifiers_are_ambiguous() -> None:
    matcher = EntityMatcher()
    first = matcher.process(record(2, "First", "first@example.com", "9000000001"))
    second = matcher.process(record(3, "Second", "second@example.com", "9000000002"))
    conflict = matcher.process(record(4, "Conflict", "first@example.com", "9000000002"))
    assert conflict.status == AMBIGUOUS_REVIEW
    assert set(conflict.candidate_entity_ids) == {first.matched_entity_id, second.matched_entity_id}
    assert conflict.conflicting_evidence


def test_actual_empty_source_row_is_invalid() -> None:
    records = records_from_source(SOURCE_CONFIGS[1])
    empty = next(item for item in records if item.source_row == 12)
    assert EntityMatcher().process(empty).status == INVALID_SOURCE_RECORD


def test_actual_shifted_source_row_is_invalid() -> None:
    records = records_from_source(SOURCE_CONFIGS[1])
    shifted = next(item for item in records if item.source_row == 20)
    assert EntityMatcher().process(shifted).status == INVALID_SOURCE_RECORD


def test_actual_embedded_header_is_invalid() -> None:
    records = records_from_source(SOURCE_CONFIGS[2])
    header = next(item for item in records if item.source_row == 16)
    assert EntityMatcher().process(header).status == INVALID_SOURCE_RECORD
