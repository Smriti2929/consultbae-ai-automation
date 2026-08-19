"""Print validation counts and sample provenance from the Phase 3 database."""

from __future__ import annotations

from src.database.db import DEFAULT_DATABASE_PATH, open_database, summary_counts


def main() -> None:
    if not DEFAULT_DATABASE_PATH.exists():
        print("Database not found. Run: python -m src.database.ingest")
        return

    with open_database() as connection:
        counts = summary_counts(connection)
        print(f"Database: {DEFAULT_DATABASE_PATH}")
        for label, value in counts.items():
            print(f"{label}: {value}")

        print("\nSample canonical persons and linked source records:")
        people = connection.execute(
            """
            SELECT id, provisional_entity_id, canonical_name,
                   canonical_email, canonical_phone, canonical_city
            FROM persons
            ORDER BY id
            LIMIT 5
            """
        ).fetchall()
        for person in people:
            print(f"\n{dict(person)}")
            linked = connection.execute(
                """
                SELECT source_filename, source_row_number, match_status,
                       raw_name, raw_email, raw_phone
                FROM source_records
                WHERE person_id = ?
                ORDER BY source_filename, source_row_number
                """,
                (person["id"],),
            ).fetchall()
            for source_record in linked:
                print(f"  {dict(source_record)}")

        print("\nUnresolved records requiring attention:")
        unresolved = connection.execute(
            """
            SELECT source_filename, source_row_number, match_status,
                   raw_name, match_reason
            FROM source_records
            WHERE person_id IS NULL
            ORDER BY source_filename, source_row_number
            """
        ).fetchall()
        for source_record in unresolved:
            print(f"  {dict(source_record)}")


if __name__ == "__main__":
    main()

