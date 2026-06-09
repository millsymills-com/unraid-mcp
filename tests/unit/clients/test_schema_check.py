"""Tests for the startup schema-compatibility check (#68)."""

from __future__ import annotations

import httpx
import pytest_asyncio
import respx

from unraid_mcp.clients.unraid import UnraidClient, compute_schema_drift

GRAPHQL_URL = "https://tower.local:443/graphql"


@pytest_asyncio.fixture
async def client():
    c = UnraidClient(graphql_url=GRAPHQL_URL, api_key="k", timeout=5, max_retries=1)
    yield c
    await c.close()


class TestComputeSchemaDrift:
    def test_no_drift_when_actual_covers_expected(self):
        expected = {"Query": frozenset({"info", "disks"})}
        actual = {"Query": {"info", "disks", "newStuff"}}
        assert compute_schema_drift(expected, actual) == []

    def test_reports_missing_fields(self):
        expected = {"Disk": frozenset({"id", "temp", "serialNum"})}
        actual = {"Disk": {"id", "serialNum"}}
        drifts = compute_schema_drift(expected, actual)
        assert len(drifts) == 1
        assert "Disk" in drifts[0]
        assert "temp" in drifts[0]

    def test_reports_type_entirely_missing(self):
        expected = {"Flash": frozenset({"guid"})}
        actual: dict[str, set[str]] = {}
        drifts = compute_schema_drift(expected, actual)
        assert len(drifts) == 1
        assert "Flash" in drifts[0]
        assert "type missing" in drifts[0]

    def test_multiple_types_accumulate(self):
        expected = {
            "Disk": frozenset({"temp"}),
            "Flash": frozenset({"guid"}),
            "Connect": frozenset({"dynamicRemoteAccessType"}),
        }
        actual = {
            "Disk": {"temperature"},  # renamed — drift
            "Flash": {"guid"},  # ok
            # Connect entirely missing
        }
        drifts = compute_schema_drift(expected, actual)
        assert len(drifts) == 2
        types_reported = {d.split(":")[0] for d in drifts}
        assert types_reported == {"Disk", "Connect"}


class TestCheckSchemaCompatibility:
    """End-to-end integration of introspection → drift report."""

    @respx.mock
    async def test_reports_no_drift_when_schema_matches(self, client, monkeypatch):
        # Pin expectations to a small set we can easily satisfy from a mock.
        monkeypatch.setattr(
            "unraid_mcp.clients.unraid.SCHEMA_EXPECTATIONS",
            {"Query": frozenset({"info"}), "Disk": frozenset({"id"})},
        )
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "__schema": {
                            "queryType": {"name": "Query"},
                            "mutationType": {"name": "Mutation"},
                            "types": [
                                {"name": "Query", "fields": [{"name": "info"}], "inputFields": None},
                                {"name": "Disk", "fields": [{"name": "id"}], "inputFields": None},
                            ],
                        },
                    },
                },
            ),
        )
        drifts = await client.check_schema_compatibility()
        assert drifts == []

    @respx.mock
    async def test_reports_drift_when_field_renamed(self, client, monkeypatch):
        # Mirrors the real #54 drift: `Disk.temp` → `Disk.temperature`.
        monkeypatch.setattr(
            "unraid_mcp.clients.unraid.SCHEMA_EXPECTATIONS",
            {"Disk": frozenset({"id", "temp"})},
        )
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "__schema": {
                            "queryType": {"name": "Query"},
                            "mutationType": {"name": "Mutation"},
                            "types": [
                                {
                                    "name": "Disk",
                                    "fields": [{"name": "id"}, {"name": "temperature"}],
                                    "inputFields": None,
                                },
                            ],
                        },
                    },
                },
            ),
        )
        drifts = await client.check_schema_compatibility()
        assert len(drifts) == 1
        assert "temp" in drifts[0]
        assert "Disk" in drifts[0]
