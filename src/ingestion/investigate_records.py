"""Targeted, read-only investigation of suspicious records and overlaps.

Comparison values are temporary pandas Series. Nothing is written to raw CSVs.
Run from the repository root with:
    python -m src.ingestion.investigate_records
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
SOURCE_1 = RAW_DIR / "source1_naukri_applicants.csv"
SOURCE_2 = RAW_DIR / "source2_gig_workers.csv"
SOURCE_3 = RAW_DIR / "source3_cbnexus_contacts.csv"
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def load_csv(path: Path) -> pd.DataFrame:
    """Load values as text so source formatting remains visible in output."""
    dataframe = pd.read_csv(path, dtype=str)
    dataframe.insert(0, "CSV row", dataframe.index + 2)
    return dataframe


def section(title: str) -> None:
    print(f"\n{title}\n{'=' * len(title)}")


def show_rows(label: str, rows: pd.DataFrame) -> None:
    print(f"\n{label} ({len(rows)} row(s))")
    print("-" * (len(label) + 12))
    print(rows.to_string(index=False) if not rows.empty else "None")


def duplicate_rows(dataframe: pd.DataFrame, column: str) -> pd.DataFrame:
    """Return every row whose non-null value occurs more than once exactly."""
    values = dataframe[column]
    return dataframe[values.notna() & values.duplicated(keep=False)]


def normalize_name(value: object) -> str | None:
    if pd.isna(value):
        return None
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def normalize_email(value: object) -> str | None:
    if pd.isna(value):
        return None
    return str(value).strip().lower()


def normalize_phone(value: object) -> str | None:
    """Create the limited phone comparison form requested for investigation."""
    if pd.isna(value):
        return None
    compact = re.sub(r"[\s\-()]", "", str(value).strip())
    digits = compact[1:] if compact.startswith("+") else compact
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits if re.fullmatch(r"\d{10}", digits) else None


def date_shape(value: str) -> str:
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", value):
        return "YYYY-MM-DD"
    if re.fullmatch(r"\d{1,2}-\d{1,2}-\d{4}", value):
        return "DD-MM-YYYY or MM-DD-YYYY"
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", value):
        return "DD/MM/YYYY or MM/DD/YYYY"
    if re.search(r"[A-Za-z]", value):
        return "day month-name year"
    return "other"


def phone_shape(value: str) -> str:
    if re.fullmatch(r"\d{10}", value):
        return "10 digits"
    if re.fullmatch(r"91\d{10}", value):
        return "12 digits with 91 prefix"
    if re.fullmatch(r"\+91-\d{10}", value):
        return "+91- plus 10 digits"
    return "other/non-phone text"


def rate_shape(value: str) -> str:
    if re.fullmatch(r"\d+/hr", value, flags=re.IGNORECASE):
        return "hourly (/hr)"
    if re.fullmatch(r"\d+(?:\.\d+)?k/month", value, flags=re.IGNORECASE):
        return "monthly (k/month)"
    return "other"


def values_exactly(dataframe: pd.DataFrame, column: str) -> None:
    print(f"\nDistinct {column} values exactly as stored:")
    for value in dataframe[column].drop_duplicates():
        print(repr(value))


def matching_pairs(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_key: str,
    right_key: str,
    label: str,
) -> pd.DataFrame:
    """Join on a temporary comparison key and retain all original columns."""
    matches = left[left[left_key].notna()].merge(
        right[right[right_key].notna()],
        left_on=left_key,
        right_on=right_key,
        suffixes=("_left", "_right"),
    )
    show_rows(label, matches.drop(columns=[left_key, right_key], errors="ignore"))
    return matches


def investigate_source_1(source: pd.DataFrame) -> None:
    section("SOURCE 1 — Naukri applicants")
    show_rows("Duplicate Full Name values", duplicate_rows(source, "Full Name"))
    show_rows("Duplicate Email values", duplicate_rows(source, "Email"))
    show_rows("Duplicate Phone values", duplicate_rows(source, "Phone"))

    ctc = pd.to_numeric(source["Current CTC"], errors="coerce")
    # The column splits evenly into small decimal-like and six/seven-digit
    # values. Show both groups because neither scale is actually dominant.
    show_rows("Current CTC below 100,000 (21-value scale group)", source[ctc < 100_000])
    show_rows("Current CTC at least 100,000 (21-value scale group)", source[ctc >= 100_000])
    values_exactly(source, "City")

    dates = source.assign(Date_Format=source["Applied Date"].map(date_shape))
    print("\nApplied Date formats (count and examples):")
    for shape, group in dates.groupby("Date_Format", sort=True):
        examples = group["Applied Date"].drop_duplicates().head(4).tolist()
        print(f"{shape}: {len(group)} row(s); examples={examples}")


def investigate_source_2(source: pd.DataFrame) -> None:
    section("SOURCE 2 — Gig workers")
    show_rows("Rows containing one or more missing values", source[source.isna().any(axis=1)])
    emails = source["email_id"]
    invalid = emails.isna() | ~emails.fillna("").str.match(EMAIL_PATTERN)
    show_rows("Invalid-looking or missing email records", source[invalid])
    show_rows("Duplicate worker_name values", duplicate_rows(source, "worker_name"))
    values_exactly(source, "status")

    rates = source[source["rate"].notna()].assign(Rate_Format=source["rate"].dropna().map(rate_shape))
    print("\nRate formats (count and examples):")
    for shape, group in rates.groupby("Rate_Format", sort=True):
        examples = group["rate"].drop_duplicates().head(5).tolist()
        print(f"{shape}: {len(group)} row(s); examples={examples}")
    values_exactly(source, "location")


def investigate_source_3(source: pd.DataFrame) -> None:
    section("SOURCE 3 — CBNexus contacts")
    header_like = source[source["Phone Number"] == "Phone Number"]
    show_rows('Rows where Phone Number equals "Phone Number"', header_like)
    print("Assessment: all five values equal their column headings, so this appears to be an embedded header.")
    show_rows("Duplicate Name values", duplicate_rows(source, "Name"))
    values_exactly(source, "Verified")

    phones = source.assign(Phone_Format=source["Phone Number"].map(phone_shape))
    print("\nPhone formats (count and examples):")
    for shape, group in phones.groupby("Phone_Format", sort=True):
        examples = group["Phone Number"].drop_duplicates().head(4).tolist()
        print(f"{shape}: {len(group)} row(s); examples={examples}")
    numeric = source["Projects Completed"].fillna("").str.fullmatch(r"\d+(?:\.\d+)?")
    show_rows("Non-numeric-looking Projects Completed values", source[~numeric])


def investigate_overlaps(one: pd.DataFrame, two: pd.DataFrame, three: pd.DataFrame) -> None:
    section("CROSS-SOURCE OVERLAP INVESTIGATION")

    one = one.assign(_name=one["Full Name"].map(normalize_name), _email=one["Email"].map(normalize_email), _phone=one["Phone"].map(normalize_phone))
    two = two.assign(_name=two["worker_name"].map(normalize_name), _email=two["email_id"].map(normalize_email))
    three = three.assign(_name=three["Name"].map(normalize_name), _phone=three["Phone Number"].map(normalize_phone))

    name_12 = matching_pairs(one, two, "_name", "_name", "Exact normalized-name overlaps: Source 1 vs Source 2")
    name_13 = matching_pairs(one, three, "_name", "_name", "Exact normalized-name overlaps: Source 1 vs Source 3")
    name_23 = matching_pairs(two, three, "_name", "_name", "Exact normalized-name overlaps: Source 2 vs Source 3")
    email_12 = matching_pairs(one, two, "_email", "_email", "Exact normalized-email overlaps: Source 1 vs Source 2")
    phone_13 = matching_pairs(one, three, "_phone", "_phone", "Exact normalized-phone overlaps: Source 1 vs Source 3")

    all_three = one[one["_name"].notna()].merge(two[two["_name"].notna()], on="_name", suffixes=("_s1", "_s2")).merge(three[three["_name"].notna()], on="_name")
    show_rows("Exact normalized-name overlaps across all three sources", all_three.drop(columns=["_name", "_email_s1", "_phone", "_email_s2"], errors="ignore"))

    name_conflict_12 = name_12[(name_12["_email_left"].notna()) & (name_12["_email_right"].notna()) & (name_12["_email_left"] != name_12["_email_right"])]
    show_rows("Same normalized name but conflicting email: Source 1 vs Source 2", name_conflict_12.drop(columns=["_name", "_email_left", "_email_right", "_phone"], errors="ignore"))
    name_conflict_13 = name_13[(name_13["_phone_left"].notna()) & (name_13["_phone_right"].notna()) & (name_13["_phone_left"] != name_13["_phone_right"])]
    show_rows("Same normalized name but conflicting phone: Source 1 vs Source 3", name_conflict_13.drop(columns=["_name", "_email", "_phone_left", "_phone_right"], errors="ignore"))

    email_name_difference = email_12[email_12["_name_left"] != email_12["_name_right"]]
    show_rows("Same normalized email but different normalized names", email_name_difference.drop(columns=["_name_left", "_name_right", "_email_left", "_email_right", "_phone"], errors="ignore"))
    phone_name_difference = phone_13[phone_13["_name_left"] != phone_13["_name_right"]]
    show_rows("Same normalized phone but different normalized names", phone_name_difference.drop(columns=["_name_left", "_name_right", "_email", "_phone_left", "_phone_right"], errors="ignore"))

    # Repeated normalized names within a source create one-to-many candidates.
    # Print the original identity evidence without choosing a winner.
    name_sets = [set(frame["_name"].dropna()) for frame in (one, two, three)]
    repeated_keys = {
        key
        for frame in (one, two, three)
        for key in frame.loc[frame["_name"].duplicated(keep=False), "_name"].dropna()
    }
    ambiguous_keys = {
        key for key in repeated_keys if sum(key in names for names in name_sets) >= 2
    }
    ambiguous = pd.concat(
        [
            one[one["_name"].isin(ambiguous_keys)].assign(Source="Source 1").rename(columns={"Full Name": "Original Name", "Email": "Original Email", "Phone": "Original Phone"}),
            two[two["_name"].isin(ambiguous_keys)].assign(Source="Source 2").rename(columns={"worker_name": "Original Name", "email_id": "Original Email"}),
            three[three["_name"].isin(ambiguous_keys)].assign(Source="Source 3").rename(columns={"Name": "Original Name", "Phone Number": "Original Phone"}),
        ],
        ignore_index=True,
    )
    columns = ["Source", "CSV row", "Original Name", "Original Email", "Original Phone", "_name"]
    show_rows("Repeated-name candidates requiring manual review", ambiguous.reindex(columns=columns).sort_values(["_name", "Source", "CSV row"]).drop(columns="_name"))


def main() -> None:
    one, two, three = map(load_csv, (SOURCE_1, SOURCE_2, SOURCE_3))
    investigate_source_1(one)
    investigate_source_2(two)
    investigate_source_3(three)
    investigate_overlaps(one, two, three)
    print("\nInvestigation complete. Raw files were read only; comparison forms were not saved.")


if __name__ == "__main__":
    main()
