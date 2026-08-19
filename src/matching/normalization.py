"""Small, reusable normalization functions for identity comparison."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _safe_text(value: Any) -> str | None:
    """Convert a present value to text; represent missing/blank values as None."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def normalize_name(value: Any) -> str | None:
    """Normalize spacing and case without changing spelling."""
    text = _safe_text(value)
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).lower()


def normalize_email(value: Any) -> str | None:
    """Return a lowercase email only when its basic structure is valid."""
    text = _safe_text(value)
    if text is None:
        return None
    normalized = text.lower()
    return normalized if EMAIL_PATTERN.fullmatch(normalized) else None


def normalize_phone(value: Any) -> str | None:
    """Return a comparable 10-digit phone without removing a leading trunk 0."""
    text = _safe_text(value)
    if text is None:
        return None

    compact = re.sub(r"[\s\-()]", "", text)
    if compact.startswith("+91") and len(compact) == 13:
        compact = compact[3:]
    elif compact.startswith("91") and len(compact) == 12:
        compact = compact[2:]

    return compact if re.fullmatch(r"\d{10}", compact) else None


def normalize_city(value: Any) -> str | None:
    """Normalize city/location spacing and case for supporting evidence only."""
    text = _safe_text(value)
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).lower()

