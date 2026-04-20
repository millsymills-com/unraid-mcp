"""Tests for the UnraidClient typed query/mutation wrapper."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from unraid_mcp.clients.unraid import UnraidClient
from unraid_mcp.errors import UnraidConnectionError

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
    async def test_list_containers_returns_empty_list_on_missing_field(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {}}))
        result = await client.list_containers()
        assert result == []


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


class TestStartArray:
    @respx.mock
    async def test_start_array_uses_set_state_mutation(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"array": {"setState": {"state": "STARTED"}}}}),
        )
        result = await client.start_array()
        assert result == {"array": {"setState": {"state": "STARTED"}}}
        sent = json.loads(route.calls[0].request.content)
        assert "array" in sent["query"]
        assert "setState" in sent["query"]
        assert "desiredState: START" in sent["query"]

    @respx.mock
    async def test_stop_array_uses_set_state_mutation(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"array": {"setState": {"state": "STOPPED"}}}}),
        )
        await client.stop_array()
        sent = json.loads(route.calls[0].request.content)
        assert "desiredState: STOP" in sent["query"]


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
        # PrefixedID (not ID) — regression guard for #59.
        assert "$id: PrefixedID!" in sent["query"]


class TestRestartContainer:
    @respx.mock
    async def test_restart_issues_stop_then_start(self, client):
        # restart_container is implemented client-side as stop → start since the
        # Unraid API 4.32+ schema no longer exposes a server-side restart mutation.
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"docker": {"stop": {"id": "abc"}}}}),
        )
        await client.restart_container("abc")
        assert route.call_count == 2
        sent0 = json.loads(route.calls[0].request.content)
        sent1 = json.loads(route.calls[1].request.content)
        assert "StopContainer" in sent0["query"]
        assert "StartContainer" in sent1["query"]


class TestStartParityCheck:
    @respx.mock
    async def test_start_parity_check_passes_correct_variable(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"parityCheck": {"start": {"running": True}}}}),
        )
        await client.start_parity_check(correct=True)
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"correct": True}
        assert "parityCheck { start(correct: $correct) }" in sent["query"]

    @respx.mock
    async def test_start_parity_check_defaults_to_false(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"parityCheck": {"start": {"running": True}}}}),
        )
        await client.start_parity_check()
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"correct": False}


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
