"""Verify every field referenced in clients/unraid.py exists in the
pinned snapshot. Runs in default pytest — no live env needed."""

from __future__ import annotations

import pytest

from tests.contract._surface import (
    SNAPSHOT_PATH,
    query_strings,
    referenced_field_names,
    schema_field_names,
)

pytestmark = pytest.mark.contract


def test_snapshot_file_exists() -> None:
    assert SNAPSHOT_PATH.exists(), (
        "snapshot.graphql missing — run `uv run python -m tests.contract.refresh` "
        "with UNRAID_API_KEY set to capture an initial snapshot."
    )


def test_every_referenced_field_exists_in_snapshot() -> None:
    """Every field name used in any client query must exist in the snapshot."""
    schema_fields = schema_field_names(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    bad: list[tuple[str, str]] = [
        (name, ref)
        for name, body in query_strings()
        for ref in referenced_field_names(body)
        if ref not in schema_fields
    ]

    assert not bad, (
        f"{len(bad)} field reference(s) in clients/unraid.py do not exist in the "
        "pinned snapshot. Either fix the typo or refresh the snapshot:\n"
        + "\n".join(f"  - {q} references unknown field '{f}'" for q, f in bad)
    )
