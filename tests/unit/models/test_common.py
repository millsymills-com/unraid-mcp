"""Tests for shared model helpers in ``unraid_mcp.models.common``."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from unraid_mcp.models.common import BigInt, _coerce_bigint


class _Sized(BaseModel):
    size: BigInt = None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (42, "42"),
        (0, "0"),
        (-1, "-1"),
        (2**63, str(2**63)),
        ("12345", "12345"),
        (None, None),
    ],
)
def test_coerce_bigint_int_and_str(raw: object, expected: str | None) -> None:
    assert _coerce_bigint(raw) == expected


def test_coerce_bigint_bool_returns_none() -> None:
    assert _coerce_bigint(True) is None
    assert _coerce_bigint(False) is None


def test_bigint_field_accepts_int_and_str() -> None:
    assert _Sized(size=42).size == "42"
    assert _Sized(size="42").size == "42"
    assert _Sized().size is None
