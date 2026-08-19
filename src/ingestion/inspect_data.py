"""Inspect raw CSV files without changing them.

Run from the repository root with:
    python -m src.ingestion.inspect_data
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
SUMMARY_PATH = PROCESSED_DATA_DIR / "inspection_summary.json"

IDENTITY_TERMS = ("name", "email", "phone", "mobile", "contact", "id")
DATE_TERMS = ("date", "dob", "birth", "created", "updated")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
NUMERIC_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")


def heading(text: str, character: str = "=") -> None:
    """Print a clear console heading."""
    print(f"\n{text}\n{character * len(text)}")


def matching_columns(columns: list[str], terms: tuple[str, ...]) -> list[str]:
    """Find columns whose normalized names contain any supplied term."""
    return [
        column
        for column in columns
        if any(term in column.lower().replace(" ", "_") for term in terms)
    ]


def non_null_text(series: pd.Series) -> pd.Series:
    """Return non-null values as strings while preserving their original text."""
    return series.dropna().astype(str)


def formatting_findings(column: str, series: pd.Series) -> dict[str, object]:
    """Collect simple, explainable warning counts for one column."""
    text = non_null_text(series)
    stripped = text.str.strip()
    lowered = stripped.str.lower()
    findings: dict[str, object] = {}

    whitespace_count = int((text != stripped).sum())
    if whitespace_count:
        findings["values_with_edge_whitespace"] = whitespace_count

    case_variants = int(
        pd.DataFrame({"original": stripped, "lowered": lowered})
        .groupby("lowered")["original"]
        .nunique()
        .gt(1)
        .sum()
    )
    if case_variants:
        findings["values_with_case_variants"] = case_variants

    duplicate_non_null = int(stripped.duplicated(keep=False).sum())
    if duplicate_non_null:
        findings["rows_with_duplicate_non_null_value"] = duplicate_non_null

    if "email" in column.lower():
        invalid_emails = int((~stripped.str.match(EMAIL_PATTERN)).sum())
        if invalid_emails:
            findings["invalid_looking_emails"] = invalid_emails

    if any(term in column.lower() for term in ("phone", "mobile", "contact")):
        formats = stripped.str.replace(r"\d", "9", regex=True).value_counts()
        findings["phone_format_patterns"] = formats.head(10).to_dict()
        digit_lengths = stripped.str.replace(r"\D", "", regex=True).str.len()
        findings["phone_digit_lengths"] = {
            str(length): int(count) for length, count in digit_lengths.value_counts().items()
        }

    if series.dtype == "object" and len(text) > 0:
        numeric_ratio = float(stripped.str.match(NUMERIC_PATTERN).mean())
        if numeric_ratio >= 0.8:
            findings["possible_numeric_text_percentage"] = round(numeric_ratio * 100, 2)

    if any(term in column.lower() for term in DATE_TERMS) and len(text) > 0:
        # Date separators and month-name usage are useful clues without changing values.
        formats = stripped.map(detect_date_shape).value_counts().to_dict()
        findings["observed_date_shapes"] = formats

    return findings


def detect_date_shape(value: str) -> str:
    """Describe the visible shape of a date value; this does not parse or alter it."""
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", value):
        return "YYYY-MM-DD"
    if re.fullmatch(r"\d{1,2}-\d{1,2}-\d{4}", value):
        return "DD-MM-YYYY or MM-DD-YYYY"
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", value):
        return "DD/MM/YYYY or MM/DD/YYYY"
    if re.search(r"[A-Za-z]", value):
        return "contains month name/text"
    return "other"


def inspect_file(csv_path: Path) -> dict[str, object]:
    """Read one CSV, print its profile, and return a JSON-friendly summary."""
    heading(f"FILE: {csv_path.name}")
    try:
        dataframe = pd.read_csv(csv_path)
    except (UnicodeDecodeError, pd.errors.ParserError, OSError) as error:
        print(f"Could not read file: {error}")
        return {"filename": csv_path.name, "error": str(error)}

    row_count, column_count = dataframe.shape
    null_counts = dataframe.isna().sum()
    null_percentages = (null_counts / row_count * 100) if row_count else null_counts.astype(float)
    duplicate_rows = int(dataframe.duplicated().sum())
    identity_columns = matching_columns(list(dataframe.columns), IDENTITY_TERMS)

    print(f"Rows: {row_count}")
    print(f"Columns: {column_count}")
    print(f"Column names: {list(dataframe.columns)}")
    print("\nDetected pandas dtypes:")
    print(dataframe.dtypes.to_string())
    print("\nFirst 5 rows:")
    print(dataframe.head(5).to_string(index=False))

    null_table = pd.DataFrame(
        {"null_count": null_counts, "null_percentage": null_percentages.round(2)}
    )
    print("\nNulls by column:")
    print(null_table.to_string())
    print(f"\nExact duplicate rows: {duplicate_rows}")
    print("\nUnique non-null values by column:")
    print(dataframe.nunique(dropna=True).to_string())
    print(f"\nLikely identity-related columns: {identity_columns or 'None detected'}")

    findings = {
        column: result
        for column in dataframe.columns
        if (result := formatting_findings(column, dataframe[column]))
    }
    print("\nSuspicious formatting patterns (warnings, not automatic conclusions):")
    if findings:
        for column, column_findings in findings.items():
            print(f"  {column}: {json.dumps(column_findings, ensure_ascii=False)}")
    else:
        print("  None found by the simple checks.")

    return {
        "filename": csv_path.name,
        "rows": row_count,
        "columns": column_count,
        "column_names": list(dataframe.columns),
        "dtypes": {column: str(dtype) for column, dtype in dataframe.dtypes.items()},
        "null_count": {column: int(value) for column, value in null_counts.items()},
        "null_percentage": {
            column: round(float(value), 2) for column, value in null_percentages.items()
        },
        "exact_duplicate_rows": duplicate_rows,
        "unique_non_null_values": {
            column: int(value) for column, value in dataframe.nunique(dropna=True).items()
        },
        "likely_identity_columns": identity_columns,
        "formatting_findings": findings,
    }


def main() -> None:
    """Inspect every CSV directly inside data/raw and save a summary."""
    csv_files = sorted(RAW_DATA_DIR.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {RAW_DATA_DIR}")
        return

    print(f"Found {len(csv_files)} CSV file(s) in {RAW_DATA_DIR}")
    summaries = [inspect_file(csv_path) for csv_path in csv_files]

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with SUMMARY_PATH.open("w", encoding="utf-8") as summary_file:
        json.dump(summaries, summary_file, indent=2, ensure_ascii=False)
    print(f"\nMachine-readable summary written to: {SUMMARY_PATH}")
    print("Raw CSV files were read only and were not modified.")


if __name__ == "__main__":
    main()
