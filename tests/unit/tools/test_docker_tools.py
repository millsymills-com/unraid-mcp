"""Tool tests for the Docker domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.models.docker import DockerContainer, DockerNetwork


class TestListContainers:
    async def test_returns_list(self, client_rw):
        client, mock = client_rw
        mock.list_containers.return_value = [
            DockerContainer(id="abc", names=["/plex"], state="running"),
            DockerContainer(id="def", names=["/sonarr"], state="exited"),
        ]
        result = await client.call_tool("unraid_list_containers")
        names = [c["names"][0] for c in result.structured_content["result"]]
        assert names == ["/plex", "/sonarr"]


class TestGetContainer:
    async def test_lookup_by_id(self, client_rw):
        client, mock = client_rw
        mock.list_containers.return_value = [
            DockerContainer(id="abc", names=["/plex"]),
            DockerContainer(id="def", names=["/sonarr"]),
        ]
        result = await client.call_tool("unraid_get_container", {"container_id": "def"})
        assert result.structured_content["id"] == "def"

    async def test_lookup_by_name_strips_leading_slash(self, client_rw):
        client, mock = client_rw
        mock.list_containers.return_value = [DockerContainer(id="abc", names=["/plex"])]
        result = await client.call_tool("unraid_get_container", {"container_id": "plex"})
        assert result.structured_content["id"] == "abc"

    async def test_miss_raises_not_found(self, client_rw):
        client, mock = client_rw
        mock.list_containers.return_value = [DockerContainer(id="abc", names=["/plex"])]
        with pytest.raises(ToolError, match="Resource not found"):
            await client.call_tool("unraid_get_container", {"container_id": "nope"})


class TestListDockerNetworks:
    async def test_returns_list(self, client_rw):
        client, mock = client_rw
        mock.list_docker_networks.return_value = [DockerNetwork(id="n1", name="bridge", driver="bridge")]
        result = await client.call_tool("unraid_list_docker_networks")
        assert result.structured_content["result"][0]["name"] == "bridge"


class TestWriteContainerOps:
    @pytest.mark.parametrize(
        ("tool_name", "client_method"),
        [
            ("unraid_start_container", "start_container"),
            ("unraid_stop_container", "stop_container"),
            ("unraid_restart_container", "restart_container"),
            ("unraid_pause_container", "pause_container"),
            ("unraid_unpause_container", "unpause_container"),
        ],
    )
    async def test_write_tool_forwards_id(self, client_rw, tool_name, client_method):
        client, mock = client_rw
        getattr(mock, client_method).return_value = {"docker": {"start": {"id": "abc"}}}
        await client.call_tool(tool_name, {"container_id": "abc"})
        getattr(mock, client_method).assert_awaited_once_with("abc")

    async def test_restart_tool_returns_client_payload(self, client_rw):
        # Drift #59: ``docker.restart`` is gone; the client reimplements
        # restart as stop → start and returns the merged payload.
        client, mock = client_rw
        mock.restart_container.return_value = {
            "stop": {"docker": {"stop": {"id": "abc"}}},
            "start": {"docker": {"start": {"id": "abc"}}},
        }
        result = await client.call_tool("unraid_restart_container", {"container_id": "abc"})
        assert set(result.structured_content.keys()) == {"stop", "start"}

    async def test_write_tool_hidden_in_readonly(self, client_ro):
        client, _ = client_ro
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool("unraid_start_container", {"container_id": "abc"})
