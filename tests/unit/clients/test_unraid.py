"""Tests for the UnraidClient typed query/mutation wrapper."""

from __future__ import annotations

import json
import re

import httpx
import pytest
import respx

from unraid_mcp.clients.unraid import UnraidClient
from unraid_mcp.errors import UnraidConnectionError, UnraidError
from unraid_mcp.models.users import User

GRAPHQL_URL = "https://tower.local:443/graphql"


@pytest.fixture
def client():
    return UnraidClient(
        graphql_url=GRAPHQL_URL,
        api_key="test-key",
        timeout=5,
        max_retries=2,
    )


class TestGetInfo:
    @respx.mock
    async def test_get_info_returns_system_info_model(self, client):
        info = {"os": {"platform": "linux"}, "cpu": {"cores": 8}}
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"info": info}}))
        result = await client.get_info()
        assert result.os is not None
        assert result.os.platform == "linux"
        assert result.cpu is not None
        assert result.cpu.cores == 8

    @respx.mock
    async def test_get_info_raises_on_missing_top_level_field(self, client):
        # Regression for #65: drop the silent ``result.get("info", {})`` —
        # missing key is a schema-drift signal.
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {}}))
        with pytest.raises(UnraidError, match="Missing 'info'"):
            await client.get_info()

    @respx.mock
    async def test_get_info_normalizes_null_to_empty_dict(self, client):
        # Present-but-null is fine — normalized to ``{}`` so model validation
        # still works against ``SystemInfo``.
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"info": None}}))
        result = await client.get_info()
        assert result.os is None


class TestGetArray:
    @respx.mock
    async def test_get_array_returns_array_state_model(self, client):
        array = {"state": "STARTED", "disks": []}
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"array": array}}))
        result = await client.get_array()
        assert result.state == "STARTED"
        assert result.disks == []

    @respx.mock
    async def test_get_array_parses_camelcase_disk_fields(self, client):
        array = {"state": "STARTED", "disks": [{"id": "d1", "numReads": 42, "fsSize": "1000"}]}
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"array": array}}))
        result = await client.get_array()
        assert result.disks is not None
        assert result.disks[0].num_reads == 42
        assert result.disks[0].fs_size == "1000"


class TestListContainers:
    @respx.mock
    async def test_list_containers_returns_list_of_models(self, client):
        containers = [{"id": "abc", "names": ["/plex"]}, {"id": "def", "names": ["/sonarr"]}]
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"dockerContainers": containers}}))
        result = await client.list_containers()
        assert [c.id for c in result] == ["abc", "def"]
        assert result[0].names == ["/plex"]

    @respx.mock
    async def test_list_containers_raises_on_missing_top_level_field(self, client):
        # Regression for #65: a missing top-level field is a schema-drift
        # signal — the client must raise instead of silently returning [].
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {}}))
        with pytest.raises(UnraidError, match="Missing 'dockerContainers'"):
            await client.list_containers()

    @respx.mock
    async def test_list_containers_normalizes_null_to_empty_list(self, client):
        # A present-but-null top-level field is allowed by the GraphQL spec
        # for nullable fields and is normalized to an empty list (#65).
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"dockerContainers": None}}))
        result = await client.list_containers()
        assert result == []

    @respx.mock
    async def test_list_containers_raises_on_wrong_type(self, client):
        # Wrong-typed top-level field is also drift. Regression for #65.
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"dockerContainers": {"not": "a list"}}})
        )
        with pytest.raises(UnraidError, match="Expected list for 'dockerContainers'"):
            await client.list_containers()


class TestListVms:
    @respx.mock
    async def test_list_vms_returns_vms_model(self, client):
        vms = {"domain": [{"uuid": "u1", "name": "win11", "state": "RUNNING"}]}
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"vms": vms}}))
        result = await client.list_vms()
        assert result.domain is not None
        assert result.domain[0].uuid == "u1"
        assert result.domain[0].name == "win11"
        assert result.domain[0].state == "RUNNING"

    @respx.mock
    async def test_list_vms_raises_on_missing_top_level_field(self, client):
        # Regression for #65: ``Vms`` is the envelope around the domain
        # list — missing it means schema drift, not "no VMs".
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {}}))
        with pytest.raises(UnraidError, match="Missing 'vms'"):
            await client.list_vms()


class TestGetFlash:
    @respx.mock
    async def test_get_flash_raises_on_missing_top_level_field(self, client):
        # Regression for #65: drop ``# type: ignore[no-any-return]`` and the
        # silent ``result.get("flash", {})`` — raise on drift.
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {}}))
        with pytest.raises(UnraidError, match="Missing 'flash'"):
            await client.get_flash()

    @respx.mock
    async def test_get_flash_normalizes_null_to_empty_dict(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"flash": None}}))
        assert await client.get_flash() == {}


class TestStartArray:
    @respx.mock
    async def test_start_array_sends_mutation(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"startArray": {"state": "STARTED"}}})
        )
        result = await client.start_array()
        assert result == {"startArray": {"state": "STARTED"}}
        sent = json.loads(route.calls[0].request.content)
        assert "startArray" in sent["query"]


class TestStartContainer:
    @respx.mock
    async def test_start_container_passes_id_variable(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={"data": {"docker": {"start": {"id": "abc", "state": "running", "status": "Up"}}}},
            )
        )
        await client.start_container("abc")
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"id": "abc"}


class TestStartParityCheck:
    @respx.mock
    async def test_start_parity_check_passes_correct_variable(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"startParityCheck": {"state": "RUNNING"}}})
        )
        await client.start_parity_check(correct=True)
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"correct": True}

    @respx.mock
    async def test_start_parity_check_defaults_to_false(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"startParityCheck": {"state": "RUNNING"}}})
        )
        await client.start_parity_check()
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"correct": False}


class TestListUsers:
    @respx.mock
    async def test_list_users_returns_user_models(self, client):
        users = [
            {"id": "u1", "name": "root", "description": "admin", "roles": "admin"},
            {"id": "u2", "name": "alice", "description": None, "roles": "user"},
        ]
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"users": users}}))
        result = await client.list_users()
        assert [u.name for u in result] == ["root", "alice"]

    @respx.mock
    async def test_list_users_query_does_not_request_password(self, client):
        # Regression for #107: never select User.password — it returns the
        # /etc/shadow hash and would land in MCP transcripts and logs.
        # Word-boundary regex so a future legitimate `passwordExpiry` field
        # would not falsely flag this assertion (#132).
        route = respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"users": []}}))
        await client.list_users()
        sent = json.loads(route.calls[0].request.content)
        assert not re.search(r"\bpassword\b", sent["query"])

    def test_user_model_has_no_password_field(self):
        # Regression for #107: even if the upstream schema starts pushing
        # `password` unsolicited, the declared model must not name it as a
        # field — this prevents accidental .password access in tools.
        assert "password" not in User.model_fields

    def test_user_model_drops_server_pushed_password(self):
        # Regression for #132: even if the Unraid server pushes `password`
        # unsolicited, `User` overrides the base `extra="allow"` to
        # `extra="ignore"` so the field is dropped before it reaches
        # `model_dump()` and the MCP tool response.
        instance = User.model_validate({"id": "u1", "name": "root", "roles": "admin", "password": "$6$shadow_hash"})
        assert "password" not in instance.model_dump()
        assert not hasattr(instance, "password")
        assert instance.model_extra == {} or instance.model_extra is None

    @respx.mock
    async def test_list_users_strips_server_pushed_password_end_to_end(self, client):
        # Regression for #132: simulate the Unraid API pushing `password`
        # unsolicited and assert it does not appear in the model_dump of
        # the value `unraid_list_users` returns to FastMCP.
        users = [
            {"id": "u1", "name": "root", "roles": "admin", "password": "$6$shadow_hash"},
        ]
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"users": users}}))
        result = await client.list_users()
        dumped = [u.model_dump() for u in result]
        assert all("password" not in u for u in dumped)


class TestCreateUser:
    @respx.mock
    async def test_create_user_with_description(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={"data": {"addUser": {"id": "u1", "name": "alice", "description": "Admin"}}},
            )
        )
        await client.create_user(name="alice", password="hunter2", description="Admin")
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"]["input"]["name"] == "alice"
        assert sent["variables"]["input"]["password"] == "hunter2"
        assert sent["variables"]["input"]["description"] == "Admin"

    @respx.mock
    async def test_create_user_without_description_omits_field(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"addUser": {"id": "u1", "name": "bob"}}})
        )
        await client.create_user(name="bob", password="hunter2")
        sent = json.loads(route.calls[0].request.content)
        assert "description" not in sent["variables"]["input"]


class TestDeleteUser:
    @respx.mock
    async def test_delete_user_passes_name(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"deleteUser": {"id": "u1", "name": "bob"}}})
        )
        await client.delete_user("bob")
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"]["input"] == {"name": "bob"}


class TestValidateConnection:
    @respx.mock
    async def test_validate_returns_none_on_success(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"info": {"os": {"platform": "linux"}}}})
        )
        assert await client.validate_connection() is None

    @respx.mock
    async def test_validate_raises_on_connection_error(self, client):
        respx.post(GRAPHQL_URL).mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(UnraidConnectionError, match="refused"):
            await client.validate_connection()

    @respx.mock
    async def test_validate_does_not_retry(self, client):
        # Regression for #34: validate_connection must fail fast without
        # the multi-attempt retry loop used by `_post`.
        route = respx.post(GRAPHQL_URL).mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(UnraidConnectionError):
            await client.validate_connection()
        assert route.call_count == 1
