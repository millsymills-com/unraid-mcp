"""Live GraphQL schema-drift detector.

Introspects the configured Unraid GraphQL endpoint, renders SDL, and compares
it to the pinned snapshot in :mod:`tests.contract`. A SHA-256 fast path passes
when nothing changed; otherwise the schemas are AST-diffed and the test fails
on breaking changes (field removed or type changed) or xfails on additive
changes (new types/fields only).

Tagged ``requires_live`` so the default pytest selection skips it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from graphql import build_client_schema, build_schema, get_introspection_query, print_schema

from unraid_mcp.clients.unraid import UnraidClient
from unraid_mcp.config import UnraidConfig

if TYPE_CHECKING:
    from graphql import GraphQLSchema
    from graphql.utilities.get_introspection_query import IntrospectionQuery

pytestmark = [pytest.mark.contract, pytest.mark.requires_live]

_SNAPSHOT_DIR = Path(__file__).parent
_SNAPSHOT_SDL = _SNAPSHOT_DIR / "snapshot.graphql"
_SNAPSHOT_SHA = _SNAPSHOT_DIR / "snapshot.sha256"


@pytest.fixture
def live_config(live_env: None) -> UnraidConfig:
    """Build a UnraidConfig from the live environment or skip the test."""
    config = UnraidConfig()
    if not config.api_enabled:
        pytest.skip("UNRAID_API_KEY not set; live schema drift test requires a real server.")
    return config


def _classify_drift(snapshot: GraphQLSchema, live: GraphQLSchema) -> tuple[list[str], list[str]]:
    """Return (breaking, additive) drift descriptions between two schemas.

    Breaking: a named type or a field on a shared type was removed, or a
    field's type signature changed. Additive: a new type or a new field on
    an existing type appeared in ``live`` but not in ``snapshot``.
    """
    snapshot_types = {name: t for name, t in snapshot.type_map.items() if not name.startswith("__")}
    live_types = {name: t for name, t in live.type_map.items() if not name.startswith("__")}

    breaking: list[str] = [f"type removed: {name}" for name in snapshot_types.keys() - live_types.keys()]
    additive: list[str] = [f"type added: {name}" for name in live_types.keys() - snapshot_types.keys()]

    for name in snapshot_types.keys() & live_types.keys():
        old_fields = getattr(snapshot_types[name], "fields", None)
        new_fields = getattr(live_types[name], "fields", None)
        if old_fields is None or new_fields is None:
            continue
        breaking.extend(f"field removed: {name}.{field}" for field in old_fields.keys() - new_fields.keys())
        additive.extend(f"field added: {name}.{field}" for field in new_fields.keys() - old_fields.keys())
        for field in old_fields.keys() & new_fields.keys():
            old_type = str(old_fields[field].type)
            new_type = str(new_fields[field].type)
            if old_type != new_type:
                breaking.append(f"field type changed: {name}.{field}: {old_type} -> {new_type}")

    return breaking, additive


async def test_live_schema_matches_snapshot(live_config: UnraidConfig) -> None:
    """Live schema must equal the pinned snapshot, or differ only additively."""
    captured_sdl = _SNAPSHOT_SDL.read_text(encoding="utf-8")
    captured_hash = _SNAPSHOT_SHA.read_text(encoding="utf-8").strip()

    assert live_config.unraid_api_key is not None  # narrowed by api_enabled check
    client = UnraidClient(
        graphql_url=live_config.graphql_url,
        api_key=live_config.unraid_api_key,
        verify_ssl=live_config.unraid_verify_ssl,
        timeout=live_config.unraid_request_timeout,
        max_retries=live_config.unraid_max_retries,
    )
    try:
        result = await client.query(get_introspection_query())
    finally:
        await client.close()

    live_schema = build_client_schema(cast("IntrospectionQuery", result))
    live_sdl = print_schema(live_schema)
    live_hash = hashlib.sha256(live_sdl.encode("utf-8")).hexdigest()

    if live_hash == captured_hash:
        return

    snapshot_schema = build_schema(captured_sdl)
    breaking, additive = _classify_drift(snapshot_schema, live_schema)

    if breaking:
        pytest.fail(
            "Breaking schema drift detected against tests/contract/snapshot.graphql:\n"
            + "\n".join(f"  - {item}" for item in breaking)
            + ("\nAdditive changes also present:\n" + "\n".join(f"  - {item}" for item in additive) if additive else "")
            + "\nReview clients/unraid.py + models, then refresh with `uv run python -m tests.contract.refresh`."
        )

    if additive:
        pytest.xfail(
            "Additive-only schema drift (informational):\n"
            + "\n".join(f"  - {item}" for item in additive)
            + "\nRefresh the snapshot with `uv run python -m tests.contract.refresh` when ready."
        )

    pytest.fail(
        "Live SDL hash differs from snapshot but AST diff found no type/field changes. "
        "Whitespace or directive ordering drift — refresh the snapshot."
    )
