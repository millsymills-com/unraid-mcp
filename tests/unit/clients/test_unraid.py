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
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"docker": {"containers": containers}}}),
        )
        result = await client.list_containers()
        assert [c.id for c in result] == ["abc", "def"]
        assert result[0].names == ["/plex"]

    @respx.mock
    async def test_list_containers_returns_empty_list_on_missing_field(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {}}))
        result = await client.list_containers()
        assert result == []

    @respx.mock
    async def test_list_containers_returns_empty_list_when_docker_null(self, client):
        # Docker socket unavailable returns {"data": {"docker": null}}; don't crash.
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"docker": None}}))
        result = await client.list_containers()
        assert result == []


class TestListDockerNetworks:
    @respx.mock
    async def test_list_docker_networks_returns_list(self, client):
        networks = [{"id": "n1", "name": "bridge", "driver": "bridge"}]
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"docker": {"networks": networks}}}),
        )
        result = await client.list_docker_networks()
        assert [n.name for n in result] == ["bridge"]


class TestListNotifications:
    @respx.mock
    async def test_list_notifications_reads_list_field(self, client):
        entries = [{"id": "n1", "title": "t", "subject": "s", "description": "d", "importance": "INFO"}]
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"notifications": {"id": "wrap", "list": entries}}}),
        )
        result = await client.list_notifications(notification_type="ARCHIVE", limit=25, offset=10)
        assert [n.id for n in result] == ["n1"]
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"type": "ARCHIVE", "limit": 25, "offset": 10}


class TestGetConnect:
    @respx.mock
    async def test_get_connect_merges_remote_access(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "connect": {"id": "c", "dynamicRemoteAccess": {"enabledType": "DISABLED"}},
                        "remoteAccess": {"accessType": "DISABLED", "forwardType": "STATIC", "port": None},
                    },
                },
            ),
        )
        result = await client.get_connect()
        assert result["dynamicRemoteAccess"]["enabledType"] == "DISABLED"
        assert result["remoteAccess"]["accessType"] == "DISABLED"


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
