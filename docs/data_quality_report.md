# Data Quality Report

## Purpose

This report records observations from the Phase 1 read-only inspection. The
warnings are candidates for investigation, not entity-matching rules.

## Initial observations

- The files contain 42 rows/8 columns, 32 rows/6 columns, and 31 rows/5
  columns respectively (counts are pandas data rows, excluding the first header).
- Column names differ across sources (`Full Name`, `worker_name`, and `Name`;
  `Email` and `email_id`; `Phone` and `Phone Number`).
- Identity coverage differs: source 1 has name, email, and phone; source 2 has
  name and email; source 3 has name and phone.
- Capitalization varies in names, emails, cities, statuses, and skill tags.
- Some values have leading or trailing whitespace, including city values.
- Phone numbers appear with country codes, leading zeroes, and punctuation.
- Application dates visibly use several formats, including ISO-style dates,
  slash-separated dates, dash-separated dates, and month names.
- Money/rate-like fields use mixed representations (plain numbers, decimals,
  hourly text, and monthly text), so their meaning and units require care.
- Exact duplicate rows, repeated field values, missing values, and per-column
  uniqueness are measured by the inspection script.
- Email syntax checks are deliberately simple. A syntactically plausible email
  is not proof that the address exists.

## File-specific findings

### `source1_naukri_applicants.csv`

- No null cells or exact duplicate rows were detected.
- Names and emails each have 41 unique values across 42 rows; phones have 40.
  These repeats are investigation candidates, not proof of duplicate people.
- Phones have both 10-digit and 12-digit representations. Pandas infers this
  column as an integer, which hides source formatting such as a leading zero or
  plus sign in the displayed dataframe.
- Five city values contain edge whitespace, and city capitalization varies.
- Four visible application-date shapes occur: ISO year-first, ambiguous
  dash-separated, ambiguous slash-separated, and month-name text.
- `Current CTC` includes values on very different scales (for example, a small
  decimal alongside six-digit values); the intended units need confirmation.

### `source2_gig_workers.csv`

- Source line 12 is `,,,,,`, producing one data row that is null in all six
  columns. It is reported and retained; the script does not delete it.
- There are no exact duplicate rows. Worker names have 30 unique non-null values
  across 31 non-null rows, while emails have 31 unique non-null values.
- Five location values contain edge whitespace. Location and status casing
  varies (for example, `Active`, `active`, and `ACTIVE`).
- `rate` is text and mixes hourly and monthly representations, so values are not
  directly comparable without later unit decisions.

### `source3_cbnexus_contacts.csv`

- Source line 16 repeats the CSV header inside the data. It remains a normal row
  in Phase 1, explaining the nonnumeric `Phone Number` and `Projects Completed`
  values reported by the inspector.
- No null cells or exact duplicate rows were detected.
- Names have 30 unique values across 31 rows; all 31 phone strings are unique.
- Phone strings use 10 digits, a 12-digit country-code form, and a punctuated
  `+91-...` form, in addition to the embedded header value.
- Four city values contain edge whitespace; city capitalization varies.
- `Verified` uses multiple spellings/cases rather than one clear boolean format.
- `Projects Completed` is mostly numeric text but is inferred as an object
  because the repeated header contributes a text value.

## Reproduce the detailed profile

Run `python -m src.ingestion.inspect_data`. Review both the console output and
`data/processed/inspection_summary.json` before proposing normalization or
matching rules.

## Targeted record investigation

The evidence below comes from `python -m src.ingestion.investigate_records`.
CSV row numbers include the header as row 1. Comparison forms exist in memory
only and are not proposed as final matching rules.

### Source 1 evidence

| Observed issue | Example/evidence | Possible implication |
|---|---|---|
| Repeated exact name | Rows 27 and 37 are both `Nikhil Chopra`; their phone, city, experience, CTC, date, and skills agree, but their emails are `alt.nikhil.chopra70@example.com` and `nikhil.chopra70@example.com`. | These records require review; name agreement alone does not explain the email difference. |
| Repeated exact email | Rows 25 (`R. Verma`) and 31 (`Rohit Verma`) both use `rohit.verma13@mailtest.example.org`. Their phone and all non-name fields also agree. | The email and phone provide stronger overlap evidence than the differing name strings, but Phase 1 does not merge them. |
| Repeated exact phone | Rows 25 and 31 use `9000000294`; rows 27 and 37 use `09000000103`. | Each phone connects a pair of internal records; neither pair is deleted. |
| Mixed CTC scales with no dominant group | Exactly 21 values are below 100,000 and 21 are at least 100,000. The smaller-scale rows are 6:`4.2`, 8:`8.3`, 14:`5.1`, 16:`6.1`, 17:`5.8`, 18:`11.2`, 19:`7.6`, 21:`2.4`, 22:`10.0`, 24:`11.9`, 25:`6.1`, 27:`7.8`, 28:`6.6`, 31:`6.1`, 32:`7.6`, 34:`2.7`, 36:`11.4`, 37:`7.8`, 39:`9.3`, 40:`5.9`, and 42:`10.3`. The other 21 values are six- or seven-digit amounts. | The column appears to mix representations or units. Because the split is even, describing either group as dominant would be unsupported. |
| City spelling/case/whitespace variants | Exact distinct values: `Bengaluru`, `GURGAON`, `pune`, `Noida`, `NOIDA`, `PUNE`, `gurugram `, `Delhi`, `new delhi`, `Noida `, `New Delhi`, `Delhi NCR`, `Pune`, `Bangalore`, `Gurugram`, `bangalore`. | Raw distinct counts overstate semantic consistency; no city equivalences are asserted here. |
| Four visible date shapes | 12 ambiguous dash-separated values (for example `24-07-2026`), 11 ambiguous slash-separated values (`07/13/2026`), 9 `YYYY-MM-DD` values (`2026-08-08`), and 10 month-name values (`7 Jul 2026`). | Slash/dash values cannot all be interpreted safely from shape alone. |

The investigation command prints all complete rows in both CTC scale groups,
including the 21 six/seven-digit records not enumerated in the compact table.

### Source 2 evidence

| Observed issue | Example/evidence | Possible implication |
|---|---|---|
| Entirely missing row | CSV row 12 is `,,,,,`; pandas reports all six fields as missing. | It is an empty source record, but it remains in the raw evidence. |
| Shifted/malformed record | Raw row 20 is `"react, javascript, mysql",ISHA.CHOPRA95@MAILTEST.EXAMPLE.ORG,Isha Chopra,1406/hr,Pune,active`. Under the six-column header, skills land in `email_id`, the email in `worker_name`, the name in `rate`, `1406/hr` in `location`, `Pune` in `status`, and `active` in `skill_tags`. | The apparent invalid email is caused by field placement, and every field on this row is suspect until its intended structure is confirmed. |
| Repeated worker name | Rows 15 and 32 are `Deepak Nair`; emails are `DEEPAK.NAIR44@EXAMPLE.COM` and `DEEPAK.NAIR57@EXAMPLE.IN`, rates are `465/hr` and `1462/hr`, and locations are `Bengaluru` and `New Delhi`. | Same name does not justify merging these records. |
| Inconsistent status vocabulary | Exact values are `Active`, `active`, `ACTIVE`, `Inactive`, `paused`, missing, and `Pune` (from malformed row 20). | Counts by raw status mix casing differences with one shifted value. |
| Mixed rate representations | 16 parsed values match hourly text such as `1415/hr`; 14 match monthly text such as `15k/month`; row 20 exposes `Isha Chopra` in the rate column because of field shifting. | Hourly and monthly values are not directly comparable, and the malformed value is not a rate. |
| Location variants and shifted data | Exact values are `Pune`, `PUNE`, `Noida `, `Delhi`, `New Delhi`, `Gurgaon`, `Noida`, `bangalore`, missing, `gurugram `, `pune`, `Bengaluru`, `1406/hr`, `NOIDA`, and `new delhi`. | `1406/hr` is evidence of row 20's shift; other differences include case and whitespace. |

### Source 3 evidence

| Observed issue | Example/evidence | Possible implication |
|---|---|---|
| Embedded header | Row 16 is exactly `Name,Phone Number,City,Verified,Projects Completed`; `Phone Number` therefore appears as a value in its own column. | Because every cell repeats its column heading, this appears to be an accidental embedded header, but it is not deleted in Phase 1. |
| Repeated name with conflicting phones | Rows 5 and 28 are both `Arjun Mehta`, with `+91-9000000131` and `9000000272`; projects are `9` and `14`. | There may be two people or multiple records; the name alone is ambiguous. |
| Inconsistent Verified vocabulary | Exact values are `Y`, `yes`, `No`, `N`, `Verified`, and `Yes`. `Verified` comes from row 16. | The field cannot be treated as a clean boolean as stored. |
| Multiple phone shapes | 13 values contain 10 digits (for example `9000000268`), 11 contain a 12-digit `91` prefix (`919000000231`), 6 use `+91-` (`+91-9000000131`), and row 16 contains `Phone Number`. | Equivalent-looking phone presentations can compare unequal without a temporary comparison form. |
| Nonnumeric project value | Row 16 contains `Projects Completed` in the `Projects Completed` column; all other values are numeric-looking. | The embedded header forces pandas to treat the whole column as text. |

## Cross-source overlap evidence

Temporary names were trimmed, repeated spaces collapsed, and lowercased;
emails were trimmed and lowercased. Phones had spaces, hyphens, and parentheses
removed, and a leading `+91`/`91` removed only when the result was exactly 10
digits. In particular, an 11-digit value beginning with `0` was **not** changed.

### Exact normalized-name candidates

- Source 1 vs Source 2 (16 distinct names; 17 row pairs because Source 2 has
  two `Deepak Nair` rows): `Arjun Mehta`, `Arjun Mishra`, `Deepak Nair`,
  `Gaurav Mehta`, `Isha Chopra`, `Isha Kapoor`, `Karan Bhatia`, `Meera Bhatia`,
  `Neha Bhatia`, `Rahul Chopra`, `Sneha Chopra`, `Tanvi Agarwal`, `Tanvi Gupta`,
  `Varun Jain`, `Varun Saxena`, and `Vikram Saxena`.
- Source 1 vs Source 3 (25 distinct names; 26 row pairs because Source 3 has
  two `Arjun Mehta` rows): `Arjun Mehta`, `Arjun Mishra`, `Deepak Mehta`,
  `Deepak Nair`, `Gaurav Mehta`, `Isha Chopra`, `Isha Kapoor`, `Karan Bhatia`,
  `Meera Bhatia`, `Neha Bhatia`, `Nikhil Mehta`, `Priya Saxena`, `Priya Singh`,
  `Rahul Chopra`, `Rahul Malhotra`, `Ritu Sharma`, `Rohit Nair`,
  `Sahil Malhotra`, `Shreya Gupta`, `Sneha Chopra`, `Tanvi Agarwal`,
  `Tanvi Gupta`, `Varun Jain`, `Varun Saxena`, and `Vikram Saxena`.
- Source 2 vs Source 3 (20 distinct names; 22 row pairs because `Arjun Mehta`
  and `Deepak Nair` expand to multiple candidates): `Arjun Mehta`,
  `Arjun Mishra`, `Deepak Nair`, `Divya Chopra`, `Gaurav Mehta`, `Isha Chopra`,
  `Isha Kapoor`, `Karan Bhatia`, `Karan Chopra`, `Manish Bhatia`, `Meera Bhatia`,
  `Neha Bhatia`, `Rahul Chopra`, `Sneha Chopra`, `Tanvi Agarwal`, `Tanvi Gupta`,
  `Varun Jain`, `Varun Saxena`, `Vikram Mehta`, and `Vikram Saxena`.

### Stronger exact field overlaps

- Source 1 vs Source 2 has 15 exact normalized-email overlaps. They belong to
  `Arjun Mishra`, `Deepak Nair` (the `44` email only), `Gaurav Mehta`,
  `Isha Chopra`, `Isha Kapoor`, `Karan Bhatia`, `Meera Bhatia`, `Neha Bhatia`,
  `Rahul Chopra`, `Sneha Chopra`, `Tanvi Agarwal`, `Tanvi Gupta`, `Varun Jain`,
  `Varun Saxena`, and `Vikram Saxena`. Original casing differences include
  `deepak.nair44@example.com` vs `DEEPAK.NAIR44@EXAMPLE.COM`.
- Source 1 vs Source 3 has 15 exact normalized-phone overlaps: `9000000106`,
  `9000000113`, `9000000133`, `9000000143`, `9000000148`, `9000000162`,
  `9000000170`, `9000000211`, `9000000227`, `9000000231`, `9000000254`,
  `9000000263`, `9000000268`, `9000000295`, and `9000000296`. Names agree in
  every one of these pairs. Examples include source 1 `+919000000254` vs source
  3 `9000000254` for `Tanvi Gupta`, and source 1 `9000000170` vs source 3
  `919000000170` for `Varun Saxena`.
- No exact normalized email or phone overlap has a differing normalized name.
  Therefore this investigation found no case where those stronger fields point
  to differently named people across the requested source pairs.

### Candidates present by name in all three sources

Sixteen normalized names occur in all three: `Arjun Mehta`, `Arjun Mishra`,
`Deepak Nair`, `Gaurav Mehta`, `Isha Chopra`, `Isha Kapoor`, `Karan Bhatia`,
`Meera Bhatia`, `Neha Bhatia`, `Rahul Chopra`, `Sneha Chopra`, `Tanvi Agarwal`,
`Tanvi Gupta`, `Varun Jain`, `Varun Saxena`, and `Vikram Saxena`.

This is an observed three-source name overlap, not proof that each set is one
person. For 14 of these names, Source 1/2 email and Source 1/3 phone evidence is
consistent after the limited comparison transformations. Exceptions and
ambiguities are recorded below.

### Conflicts and ambiguous candidates

| Observed issue | Original evidence | Possible implication |
|---|---|---|
| `Arjun Mehta` is a one-to-many name candidate | Source 1 row 20: `Arjun Mehta`, `arjun.mehta9@example.in`, `09000000131`. Source 2 row 18: `Arjun Mehta`, `arjun.mehta77@mailtest.example.org`. Source 3 row 5: `Arjun Mehta`, `+91-9000000131`; Source 3 row 28: `Arjun Mehta`, `9000000272`. | Source 1's leading-zero phone visually resembles source 3 row 5 after a transformation that was not authorized here, while row 28 has a different phone and Source 2 has a different email. Do not automatically merge this group. |
| `Deepak Nair` is a one-to-many name candidate | Source 1 row 33: `Deepak Nair`, `deepak.nair44@example.com`, `9000000296`. Source 2 rows 15 and 32: `Deepak Nair`, respectively `DEEPAK.NAIR44@EXAMPLE.COM` and `DEEPAK.NAIR57@EXAMPLE.IN`. Source 3 row 25: `DEEPAK NAIR`, `919000000296`. | The `44` email and phone support one path, while Source 2's `57` record shares only the name. Do not attach both Source 2 rows automatically. |
| Same name but email conflict | In addition to `Deepak Nair`, Source 1 `Arjun Mehta` uses `arjun.mehta9@example.in` while Source 2 uses `arjun.mehta77@mailtest.example.org`. | Exact name alone is insufficient evidence. |
| Same name but phone comparison conflict | Leading-zero Source 1 values do not normalize under the specified rule: `Deepak Mehta` `09000000116` vs `9000000116`; `Isha Chopra` `09000000138` vs `919000000138`; `Meera Bhatia` `09000000223` vs `919000000223`; `Neha Bhatia` `09000000273` vs `9000000273`; `Nikhil Mehta` `09000000104` vs `+91-9000000104`; `Priya Singh` `09000000287` vs `9000000287`; `Rahul Chopra` `09000000137` vs `9000000137`; `Rahul Malhotra` `09000000260` vs `919000000260`; and `Ritu Sharma` `09000000146` vs `9000000146`. | These strings are visually related but are not exact results of the approved comparison transformation. They remain manual-review candidates rather than phone matches. |

The console investigation prints the complete original rows for every pairwise
name, email, and phone candidate, including all one-to-many combinations. No
cleaned comparison field is written to disk and no merge decision is made.

## Phase 2 handling decisions

These are handling decisions added after the Phase 1 observations above. They
do not revise or erase the original findings.

| Observed issue | Phase 2 evidence/handling | Possible implication |
|---|---|---|
| Empty Source 2 row | Classified `INVALID_SOURCE_RECORD`; the row and reason remain in the audit. | It contributes no provisional person entity but remains accounted for. |
| Shifted Source 2 row 20 | Classified `INVALID_SOURCE_RECORD` because email/name/rate/location values occupy incompatible declared fields. No automatic repair is attempted. | The likely `Isha Chopra` identity cannot participate through unreliable field alignment. |
| Source 3 embedded header | Classified `INVALID_SOURCE_RECORD`; no field from it is indexed as an identifier. | Header text cannot accidentally create a person entity. |
| Valid normalized email or phone points to one entity | Classified `MATCHED_HIGH_CONFIDENCE`, with the exact evidence field and provisional entity ID recorded. | The attachment is deterministic and reviewable, but provisional IDs are not final database records. |
| Name-only overlap | Classified `AMBIGUOUS_REVIEW`; candidate entity IDs are shown and no attachment occurs. | Known repeated-name cases remain separate pending human judgment. |
| Email and phone point to different entities | Classified `AMBIGUOUS_REVIEW` with both field-to-entity mappings. This path is covered by a unit test even though it does not occur in the current files. | A future conflict cannot be silently resolved by field precedence. |
| Leading-zero phone | Remains invalid for strong-phone matching because Phase 2 does not remove an Indian trunk-prefix `0`. | Visually related pairs documented in Phase 1 remain review cases. |

The generated `matching_audit.json` and `matching_audit.csv` contain one decision
for each of the 105 source data rows: 53 `NEW_ENTITY`, 31
`MATCHED_HIGH_CONFIDENCE`, 18 `AMBIGUOUS_REVIEW`, and 3
`INVALID_SOURCE_RECORD`. The 53 entity IDs are provisional audit constructs,
not a canonical database.
