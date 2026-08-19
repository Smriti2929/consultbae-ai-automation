"""Explainable deterministic matching using email and phone as strong IDs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


MATCHED_HIGH_CONFIDENCE = "MATCHED_HIGH_CONFIDENCE"
NEW_ENTITY = "NEW_ENTITY"
AMBIGUOUS_REVIEW = "AMBIGUOUS_REVIEW"
INVALID_SOURCE_RECORD = "INVALID_SOURCE_RECORD"


@dataclass
class SourceRecord:
    source_system: str
    source_file: str
    source_row: int
    raw_name: str | None = None
    raw_email: str | None = None
    raw_phone: str | None = None
    raw_city: str | None = None
    normalized_name: str | None = None
    normalized_email: str | None = None
    normalized_phone: str | None = None
    normalized_city: str | None = None
    invalid_reason: str | None = None
    raw_record: dict[str, Any] = field(default_factory=dict)


@dataclass
class Entity:
    entity_id: str
    record_references: list[str] = field(default_factory=list)
    names: set[str] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    phones: set[str] = field(default_factory=set)
    cities: set[str] = field(default_factory=set)


@dataclass
class MatchDecision:
    record: SourceRecord
    status: str
    matched_entity_id: str | None
    evidence: list[str]
    reason: str
    candidate_entity_ids: list[str] = field(default_factory=list)
    conflicting_evidence: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        output = asdict(self)
        output.update(output.pop("record"))
        return output


class EntityMatcher:
    """Process records sequentially while keeping every decision auditable."""

    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}
        self.email_index: dict[str, str] = {}
        self.phone_index: dict[str, str] = {}
        self.next_entity_number = 1

    def process(self, record: SourceRecord) -> MatchDecision:
        if record.invalid_reason:
            return MatchDecision(
                record=record,
                status=INVALID_SOURCE_RECORD,
                matched_entity_id=None,
                evidence=[],
                reason=record.invalid_reason,
            )

        email_entity = self.email_index.get(record.normalized_email or "")
        phone_entity = self.phone_index.get(record.normalized_phone or "")
        strong_candidates = {item for item in (email_entity, phone_entity) if item}

        if len(strong_candidates) > 1:
            return MatchDecision(
                record=record,
                status=AMBIGUOUS_REVIEW,
                matched_entity_id=None,
                evidence=["normalized_email", "normalized_phone"],
                reason="Email and phone point to different existing entities.",
                candidate_entity_ids=sorted(strong_candidates),
                conflicting_evidence={
                    "normalized_email": [email_entity] if email_entity else [],
                    "normalized_phone": [phone_entity] if phone_entity else [],
                },
            )

        if len(strong_candidates) == 1:
            entity_id = strong_candidates.pop()
            evidence = []
            if email_entity == entity_id:
                evidence.append("normalized_email")
            if phone_entity == entity_id:
                evidence.append("normalized_phone")
            self._attach(record, self.entities[entity_id])
            return MatchDecision(
                record=record,
                status=MATCHED_HIGH_CONFIDENCE,
                matched_entity_id=entity_id,
                evidence=evidence,
                reason=f"Exact valid {' and '.join(evidence)} match to {entity_id}.",
                candidate_entity_ids=[entity_id],
            )

        name_candidates = self._entities_with_name(record.normalized_name)
        if name_candidates:
            reason = "Exact normalized name is supporting evidence only; no strong identifier resolves the match."
            if len(name_candidates) > 1:
                reason = "Multiple existing entities share the normalized name and no strong identifier resolves the match."
            return MatchDecision(
                record=record,
                status=AMBIGUOUS_REVIEW,
                matched_entity_id=None,
                evidence=["normalized_name"],
                reason=reason,
                candidate_entity_ids=name_candidates,
            )

        entity = self._create_entity(record)
        return MatchDecision(
            record=record,
            status=NEW_ENTITY,
            matched_entity_id=entity.entity_id,
            evidence=[],
            reason="No existing entity has the same valid email or phone; no name-review candidate was found.",
        )

    def _create_entity(self, record: SourceRecord) -> Entity:
        entity_id = f"ENTITY-{self.next_entity_number:04d}"
        self.next_entity_number += 1
        entity = Entity(entity_id=entity_id)
        self.entities[entity_id] = entity
        self._attach(record, entity)
        return entity

    def _attach(self, record: SourceRecord, entity: Entity) -> None:
        reference = f"{record.source_file}:row-{record.source_row}"
        entity.record_references.append(reference)
        if record.normalized_name:
            entity.names.add(record.normalized_name)
        if record.normalized_email:
            entity.emails.add(record.normalized_email)
            self.email_index[record.normalized_email] = entity.entity_id
        if record.normalized_phone:
            entity.phones.add(record.normalized_phone)
            self.phone_index[record.normalized_phone] = entity.entity_id
        if record.normalized_city:
            entity.cities.add(record.normalized_city)

    def _entities_with_name(self, normalized_name: str | None) -> list[str]:
        if normalized_name is None:
            return []
        return sorted(
            entity.entity_id
            for entity in self.entities.values()
            if normalized_name in entity.names
        )

