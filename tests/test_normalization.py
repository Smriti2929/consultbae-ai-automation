import pytest

from src.matching.normalization import (
    normalize_city,
    normalize_email,
    normalize_name,
    normalize_phone,
)


def test_name_normalization() -> None:
    assert normalize_name("  RITU   SHARMA ") == "ritu sharma"


def test_email_normalization() -> None:
    assert normalize_email(" Person@Example.COM ") == "person@example.com"


@pytest.mark.parametrize("value", [None, "", "not-an-email", "a@b", "a b@example.com"])
def test_malformed_email_returns_none(value: object) -> None:
    assert normalize_email(value) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("9000000131", "9000000131"),
        ("919000000131", "9000000131"),
        ("+91-9000000131", "9000000131"),
        ("+91 (90000) 00131", "9000000131"),
    ],
)
def test_phone_normalization(value: str, expected: str) -> None:
    assert normalize_phone(value) == expected


@pytest.mark.parametrize("value", ["Phone Number", "123", "09000000131", None])
def test_invalid_phone_returns_none(value: object) -> None:
    assert normalize_phone(value) is None


def test_city_normalization() -> None:
    assert normalize_city("  New   Delhi ") == "new delhi"

