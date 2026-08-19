"""Generate Phase 2 matching audit reports without creating a database."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from src.matching.entity_resolution import EntityMatcher, MatchDecision, SourceRecord
from src.matching.normalization import (
    normalize_city,
    normalize_email,
    normalize_name,
    normalize_phone,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
JSON_REPORT = OUTPUT_DIR / "matching_audit.json"
CSV_REPORT = OUTPUT_DIR / "matching_audit.csv"

SOURCE_CONFIGS = [
    {
        "system": "Naukri applicants",
        "file": "source1_naukri_applicants.csv",
        "name": "Full Name",
        "email": "Email",
        "phone": "Phone",
        "city": "City",
    },
    {
        "system": "Gig workers",
        "file": "source2_gig_workers.csv",
        "name": "worker_name",
        "email": "email_id",
        "phone": None,
        "city": "location",
    },
    {
        "system": "CBNexus contacts",
        "file": "source3_cbnexus_contacts.csv",
        "name": "Name",
        "email": None,
        "phone": "Phone Number",
        "city": "City",
    },
]


def clean_raw_value(value: Any) -> str | None:
    """Make pandas missing values JSON-safe without changing present strings."""
    return None if value is None or pd.isna(value) else str(value)


def invalid_reason(raw: dict[str, str | None], config: dict[str, str | None]) -> str | None:
    values = list(raw.values())
    if all(value is None or not value.strip() for value in values):
        return "Completely empty source row; it cannot reasonably represent a person."

    if all(raw.get(column) == column for column in raw):
        return "Every value repeats its column heading; this is an embedded header row."

    if config["system"] == "Gig workers":
        email_value = raw.get("email_id") or ""
        worker_value = raw.get("worker_name") or ""
        rate_value = raw.get("rate") or ""
        location_value = raw.get("location") or ""
        shifted = (
            normalize_email(email_value) is None
            and normalize_email(worker_value) is not None
            and re.fullmatch(r"\d+/hr", location_value) is not None
            and re.search(r"[A-Za-z]", rate_value) is not None
        )
        if shifted:
            return "Fields appear shifted: identity values are not in their declared columns, so the record is unreliable."

    return None


def records_from_source(config: dict[str, str | None]) -> list[SourceRecord]:
    path = RAW_DIR / str(config["file"])
    dataframe = pd.read_csv(path, dtype=str)
    records: list[SourceRecord] = []

    for index, row in dataframe.iterrows():
        raw = {column: clean_raw_value(row[column]) for column in dataframe.columns}
        raw_name = raw.get(str(config["name"])) if config["name"] else None
        raw_email = raw.get(str(config["email"])) if config["email"] else None
        raw_phone = raw.get(str(config["phone"])) if config["phone"] else None
        raw_city = raw.get(str(config["city"])) if config["city"] else None
        records.append(
            SourceRecord(
                source_system=str(config["system"]),
                source_file=str(config["file"]),
                source_row=index + 2,
                raw_name=raw_name,
                raw_email=raw_email,
                raw_phone=raw_phone,
                raw_city=raw_city,
                normalized_name=normalize_name(raw_name),
                normalized_email=normalize_email(raw_email),
                normalized_phone=normalize_phone(raw_phone),
                normalized_city=normalize_city(raw_city),
                invalid_reason=invalid_reason(raw, config),
                raw_record=raw,
            )
        )
    return records


def generate_decisions() -> tuple[list[MatchDecision], EntityMatcher]:
    matcher = EntityMatcher()
    decisions = [
        matcher.process(record)
        for config in SOURCE_CONFIGS
        for record in records_from_source(config)
    ]
    return decisions, matcher


def write_reports(decisions: list[MatchDecision]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = [decision.to_dict() for decision in decisions]
    JSON_REPORT.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    csv_fields = [
        "source_system", "source_file", "source_row", "raw_name", "raw_email",
        "raw_phone", "raw_city", "normalized_name", "normalized_email",
        "normalized_phone", "normalized_city", "status", "matched_entity_id",
        "evidence", "reason", "candidate_entity_ids", "conflicting_evidence",
        "invalid_reason", "raw_record",
    ]
    with CSV_REPORT.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=csv_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(row[key], ensure_ascii=False)
                if isinstance(row.get(key), (list, dict)) else row.get(key)
                for key in csv_fields
            })


def main() -> None:
    decisions, matcher = generate_decisions()
    write_reports(decisions)
    counts = Counter(decision.status for decision in decisions)

    print(f"Processed {len(decisions)} source records into {len(matcher.entities)} provisional entities.")
    for status in sorted(counts):
        print(f"{status}: {counts[status]}")
    print(f"JSON audit: {JSON_REPORT}")
    print(f"CSV audit:  {CSV_REPORT}")
    print("Raw CSV files were read only and were not modified.")


if __name__ == "__main__":
    main()

