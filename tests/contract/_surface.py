"""Shared parsing of the pinned snapshot and the client's GraphQL operations.

Used by the contract tests to relate what ``clients/unraid.py`` actually
queries to what the snapshot schema exposes. No live env needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graphql import Visitor, build_schema, parse, visit
from graphql.language.ast import FieldNode, OperationDefinitionNode, OperationType

_OP_TO_LABEL = {
    OperationType.QUERY: "Query",
    OperationType.MUTATION: "Mutation",
    OperationType.SUBSCRIPTION: "Subscription",
}

_CONTRACT_DIR = Path(__file__).parent
SNAPSHOT_PATH = _CONTRACT_DIR / "snapshot.graphql"
CLIENT_PATH = _CONTRACT_DIR.parents[1] / "src/unraid_mcp/clients/unraid.py"

_ROOT_LABELS = ("Query", "Mutation", "Subscription")


def query_strings() -> list[tuple[str, str]]:
    """Return ``[(name, body)]`` for every ``QUERY_*``/``MUTATION_*`` constant."""
    text = CLIENT_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r'((?:QUERY|MUTATION)_\w+)\s*=\s*"""(.*?)"""', re.DOTALL)
    return pattern.findall(text)


class _FieldCollector(Visitor):
    def __init__(self) -> None:
        super().__init__()
        self.names: set[str] = set()

    def enter(self, node: Any, *_: Any) -> None:
        if isinstance(node, FieldNode):
            self.names.add(node.name.value)


def referenced_field_names(query_body: str) -> set[str]:
    """Every field name selected anywhere in one operation body."""
    collector = _FieldCollector()
    visit(parse(query_body), collector)
    return collector.names


def all_referenced_field_names() -> set[str]:
    """Every field name selected across all client operations."""
    names: set[str] = set()
    for _, body in query_strings():
        names |= referenced_field_names(body)
    return names


def invoked_root_fields() -> dict[str, set[str]]:
    """Top-level selection field names per root type across client operations.

    Keyed by ``Query``/``Mutation``/``Subscription``. Only direct children of
    each operation's selection set — the actual root fields the client invokes.
    Nested selections are excluded so a root field is never falsely counted as
    covered because a deeper field happens to share its name. Splitting by root
    prevents a read-side name (e.g. ``Query.docker``) from masking lost
    write-side coverage of a same-named ``Mutation`` field.
    """
    by_root: dict[str, set[str]] = {label: set() for label in _ROOT_LABELS}
    for _, body in query_strings():
        for definition in parse(body).definitions:
            if isinstance(definition, OperationDefinitionNode):
                by_root[_OP_TO_LABEL[definition.operation]] |= {
                    selection.name.value
                    for selection in definition.selection_set.selections
                    if isinstance(selection, FieldNode)
                }
    return by_root


def schema_field_names(sdl: str) -> set[str]:
    """Every field name on every object/interface type in the schema."""
    schema = build_schema(sdl)
    names: set[str] = set()
    for type_ in schema.type_map.values():
        fields = getattr(type_, "fields", None)
        if fields:
            names.update(fields.keys())
    return names


def root_field_names(sdl: str) -> dict[str, set[str]]:
    """Map ``Query``/``Mutation``/``Subscription`` to their root field names."""
    schema = build_schema(sdl)
    roots = (schema.query_type, schema.mutation_type, schema.subscription_type)
    return {label: set(root.fields) if root else set() for label, root in zip(_ROOT_LABELS, roots, strict=True)}


@dataclass(frozen=True)
class CoverageViolations:
    """Per-root-type registry rot, classified into the ratchet's three arms.

    Each attribute is sorted for stable assertion messages.

    Attributes:
        unaccounted: Schema root fields that are neither invoked by a client
            operation nor listed in the declined registry — the gap the ratchet
            exists to catch.
        now_covered: Declined fields a tool now invokes; the registry entry is
            stale and should be dropped.
        phantom: Declined fields absent from the schema; the registry entry
            points at nothing and should be dropped.
    """

    unaccounted: list[str]
    now_covered: list[str]
    phantom: list[str]


def classify_coverage(schema_fields: set[str], invoked: set[str], declined: set[str]) -> CoverageViolations:
    """Partition coverage state into the ratchet's three violation arms.

    Pure comparison over name sets for a single root type — no schema parsing,
    no client introspection — so it can be driven with synthetic inputs.

    Args:
        schema_fields: Root field names the snapshot schema exposes.
        invoked: Root field names a client operation selects (covered).
        declined: Root field names listed as intentionally uncovered.

    Returns:
        A :class:`CoverageViolations` with each arm populated.
    """
    return CoverageViolations(
        unaccounted=sorted(schema_fields - invoked - declined),
        now_covered=sorted(declined & invoked),
        phantom=sorted(declined - schema_fields),
    )
