"""Verify every field referenced in clients/unraid.py exists in the
pinned snapshot. Runs in default pytest — no live env needed."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from graphql import Visitor, build_schema, parse, visit
from graphql.language.ast import FieldNode

pytestmark = pytest.mark.contract

_SDL_PATH = Path(__file__).parent / "snapshot.graphql"
_CLIENT_PATH = Path(__file__).parents[2] / "src/unraid_mcp/clients/unraid.py"


def _query_strings() -> list[tuple[str, str]]:
    """Return [(name, body)] for every QUERY_*/MUTATION_* in the client."""
    text = _CLIENT_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r'((?:QUERY|MUTATION)_\w+)\s*=\s*"""(.*?)"""', re.DOTALL)
    return pattern.findall(text)


class _FieldCollector(Visitor):
    def __init__(self) -> None:
        super().__init__()
        self.names: set[str] = set()

    def enter(self, node: Any, *_: Any) -> None:
        if isinstance(node, FieldNode):
            self.names.add(node.name.value)


def _referenced_field_names(query_body: str) -> set[str]:
    document = parse(query_body)
    collector = _FieldCollector()
    visit(document, collector)
    return collector.names


def _all_field_names_in_schema(sdl: str) -> set[str]:
    schema = build_schema(sdl)
    names: set[str] = set()
    for type_ in schema.type_map.values():
        fields = getattr(type_, "fields", None)
        if fields:
            names.update(fields.keys())
    return names


def test_snapshot_file_exists() -> None:
    assert _SDL_PATH.exists(), (
        "snapshot.graphql missing — run `uv run python -m tests.contract.refresh` "
        "with UNRAID_API_KEY set to capture an initial snapshot."
    )


def test_every_referenced_field_exists_in_snapshot() -> None:
    """Every field name used in any client query must exist in the snapshot."""
    sdl = _SDL_PATH.read_text(encoding="utf-8")
    schema_fields = _all_field_names_in_schema(sdl)

    bad: list[tuple[str, str]] = [
        (name, ref)
        for name, body in _query_strings()
        for ref in _referenced_field_names(body)
        if ref not in schema_fields
    ]

    assert not bad, (
        f"{len(bad)} field reference(s) in clients/unraid.py do not exist in the "
        f"pinned snapshot. Either fix the typo or refresh the snapshot:\n"
        + "\n".join(f"  - {q} references unknown field '{f}'" for q, f in bad)
    )
