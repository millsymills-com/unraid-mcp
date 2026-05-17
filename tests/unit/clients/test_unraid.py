"""Tests for the UnraidClient typed query/mutation wrapper."""

from __future__ import annotations

import json
import re

import httpx
import pytest
import respx

from unraid_mcp.clients.unraid import UnraidClient
from unraid_mcp.errors import UnraidConnectionError, UnraidError, UnraidNotFoundError
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
        # Unraid API 4.32+ groups the container list under ``docker.containers``.
        containers = [{"id": "abc", "names": ["/plex"]}, {"id": "def", "names": ["/sonarr"]}]
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"docker": {"containers": containers}}}),
        )
        result = await client.list_containers()
        assert [c.id for c in result] == ["abc", "def"]
        assert result[0].names == ["/plex"]

    @respx.mock
    async def test_list_containers_raises_on_missing_top_level_field(self, client):
        # Regression for #65: a missing top-level field is a schema-drift
        # signal — the client must raise instead of silently returning [].
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {}}))
        with pytest.raises(UnraidError, match="Missing 'docker'"):
            await client.list_containers()

    @respx.mock
    async def test_list_containers_normalizes_null_docker_to_empty_list(self, client):
        # Docker daemon unavailable returns {"data": {"docker": null}}; treat
        # like an empty roster rather than raising — drift only fires for a
        # missing top-level key, not a present-but-null one (#55).
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"docker": None}}))
        result = await client.list_containers()
        assert result == []

    @respx.mock
    async def test_list_containers_normalizes_null_containers_to_empty_list(self, client):
        # ``docker.containers: null`` is the same idea one level deeper.
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"docker": {"containers": None}}}),
        )
        result = await client.list_containers()
        assert result == []

    @respx.mock
    async def test_list_containers_raises_on_wrong_type(self, client):
        # Wrong-typed nested field is also drift. Regression for #65.
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={"data": {"docker": {"containers": {"not": "a list"}}}},
            ),
        )
        with pytest.raises(UnraidError, match=re.escape("Expected list for 'docker.containers'")):
            await client.list_containers()


class TestListDockerNetworks:
    @respx.mock
    async def test_list_docker_networks_returns_list(self, client):
        # Unraid API 4.32+ groups the network list under ``docker.networks``.
        networks = [{"id": "n1", "name": "bridge", "driver": "bridge"}]
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"docker": {"networks": networks}}}),
        )
        result = await client.list_docker_networks()
        assert [n.name for n in result] == ["bridge"]

    @respx.mock
    async def test_list_docker_networks_normalizes_null_docker_to_empty_list(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"docker": None}}))
        result = await client.list_docker_networks()
        assert result == []


class TestListNotifications:
    @respx.mock
    async def test_list_notifications_reads_list_field(self, client):
        # Unraid API 4.32+ wraps entries under ``notifications.list(filter)``.
        entries = [{"id": "n1", "title": "t", "subject": "s", "description": "d", "importance": "INFO"}]
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"notifications": {"id": "wrap", "list": entries}}}),
        )
        result = await client.list_notifications(notification_type="ARCHIVE", limit=25, offset=10)
        assert [n.id for n in result] == ["n1"]
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"type": "ARCHIVE", "limit": 25, "offset": 10}

    @respx.mock
    async def test_list_notifications_defaults_to_unread(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"notifications": {"id": "wrap", "list": []}}}),
        )
        result = await client.list_notifications()
        assert result == []
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"type": "UNREAD", "limit": 50, "offset": 0}

    @respx.mock
    async def test_list_notifications_normalizes_null_list_to_empty(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"notifications": {"id": "wrap", "list": None}}}),
        )
        result = await client.list_notifications()
        assert result == []


class TestGetConnect:
    @respx.mock
    async def test_get_connect_merges_remote_access(self, client):
        # Unraid API 4.32+ splits the legacy ``connect.config`` fields out to a
        # sibling top-level ``remoteAccess`` query; the client merges both into
        # one combined dict.
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
        vms = {"domain": [{"id": "u1", "name": "win11", "state": "RUNNING"}]}
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"vms": vms}}))
        result = await client.list_vms()
        assert result.domain is not None
        assert result.domain[0].id == "u1"
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

    @respx.mock
    async def test_get_flash_query_omits_guid(self, client):
        # Regression for #52: requesting ``Flash.guid`` triggers a
        # non-null violation on trial/unregistered Unraid installs.
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"flash": {"vendor": "SanDisk", "product": "Cruzer"}}}),
        )
        result = await client.get_flash()
        assert result == {"vendor": "SanDisk", "product": "Cruzer"}
        sent = json.loads(route.calls[0].request.content)
        assert "vendor" in sent["query"]
        assert "product" in sent["query"]
        assert "guid" not in sent["query"]


class TestStartArray:
    @respx.mock
    async def test_start_array_sends_grouped_mutation(self, client):
        # Unraid API 4.32+ groups array lifecycle mutations under
        # ``array.setState(input: {desiredState: START | STOP})``.
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={"data": {"array": {"setState": {"state": "STARTED"}}}},
            )
        )
        result = await client.start_array()
        assert result == {"array": {"setState": {"state": "STARTED"}}}
        sent = json.loads(route.calls[0].request.content)
        assert "array" in sent["query"]
        assert "setState" in sent["query"]
        assert "desiredState: START" in sent["query"]


class TestStopArray:
    @respx.mock
    async def test_stop_array_sends_grouped_mutation(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={"data": {"array": {"setState": {"state": "STOPPED"}}}},
            )
        )
        await client.stop_array()
        sent = json.loads(route.calls[0].request.content)
        assert "desiredState: STOP" in sent["query"]


class TestStartContainer:
    @respx.mock
    async def test_start_container_passes_prefixed_id_variable(self, client):
        # Drift #59: ``$id`` is typed as ``PrefixedID!`` on Unraid API 4.32+.
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={"data": {"docker": {"start": {"id": "abc", "state": "running", "status": "Up"}}}},
            )
        )
        await client.start_container("abc")
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"id": "abc"}
        assert "$id: PrefixedID!" in sent["query"]


class TestRestartContainer:
    @respx.mock
    async def test_restart_container_emits_stop_then_start(self, client):
        # Drift #59: ``docker.restart`` was removed; the client now
        # reimplements restart as a client-side stop → start.
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={"data": {"docker": {"start": {"id": "abc", "state": "running", "status": "Up"}}}},
            )
        )
        result = await client.restart_container("abc")
        assert route.call_count == 2
        first = json.loads(route.calls[0].request.content)
        second = json.loads(route.calls[1].request.content)
        assert "StopContainer" in first["query"]
        assert "StartContainer" in second["query"]
        assert first["variables"] == {"id": "abc"}
        assert second["variables"] == {"id": "abc"}
        assert set(result.keys()) == {"stop", "start"}

    @respx.mock
    async def test_restart_container_returns_merged_stop_and_start_payloads(self, client):
        # Issue #164: success path must surface both underlying mutation
        # responses under their respective keys so callers can inspect
        # the GraphQL data from each step.
        stop_payload = {"docker": {"stop": {"id": "abc", "state": "exited", "status": "Exited"}}}
        start_payload = {"docker": {"start": {"id": "abc", "state": "running", "status": "Up"}}}
        responses = [
            httpx.Response(200, json={"data": stop_payload}),
            httpx.Response(200, json={"data": start_payload}),
        ]
        respx.post(GRAPHQL_URL).mock(side_effect=responses)
        result = await client.restart_container("abc")
        assert result == {"stop": stop_payload, "start": start_payload}

    @respx.mock
    async def test_restart_container_raises_with_partial_failure_message_when_start_fails(self, client):
        # Issue #164: if stop succeeds but start fails, the container is
        # left stopped — the raised UnraidError must say so and chain
        # the original via __cause__ so operators can trace the
        # underlying GraphQL failure.
        stop_payload = {"docker": {"stop": {"id": "abc", "state": "exited", "status": "Exited"}}}
        responses = [
            httpx.Response(200, json={"data": stop_payload}),
            httpx.Response(
                200,
                json={"errors": [{"message": "docker daemon refused start"}]},
            ),
        ]
        route = respx.post(GRAPHQL_URL).mock(side_effect=responses)
        with pytest.raises(UnraidError, match="was stopped successfully") as exc_info:
            await client.restart_container("abc")
        assert route.call_count == 2
        assert "unraid_start_container" in str(exc_info.value)
        assert "'abc'" in str(exc_info.value)
        # Original GraphQL failure must be chained for diagnostics.
        assert isinstance(exc_info.value.__cause__, UnraidError)

    @respx.mock
    async def test_restart_container_propagates_stop_failure_unchanged(self, client):
        # Issue #164: when the stop itself fails there is no partial
        # state to report — the underlying exception must propagate
        # unchanged (no rewrap, no "was stopped successfully" message),
        # and the start mutation must never be issued.
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={"errors": [{"message": "docker daemon refused stop"}]},
            ),
        )
        with pytest.raises(UnraidError) as exc_info:
            await client.restart_container("abc")
        assert route.call_count == 1
        assert "was stopped successfully" not in str(exc_info.value)
        assert "docker daemon refused stop" in str(exc_info.value)


class TestStartParityCheck:
    @respx.mock
    async def test_start_parity_check_sends_grouped_mutation(self, client):
        # Unraid API 4.32+ groups parity mutations under
        # ``parityCheck.{start,pause,resume,cancel}`` and returns JSON-ish
        # (no typed selection set).
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"parityCheck": {"start": True}}})
        )
        await client.start_parity_check(correct=True)
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"correct": True}
        assert "parityCheck" in sent["query"]
        assert "start(correct: $correct)" in sent["query"]

    @respx.mock
    async def test_start_parity_check_defaults_to_false(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"parityCheck": {"start": True}}})
        )
        await client.start_parity_check()
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"correct": False}


class TestParityPauseResumeCancel:
    @respx.mock
    async def test_pause_parity_check_uses_grouped_field(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"parityCheck": {"pause": True}}})
        )
        await client.pause_parity_check()
        sent = json.loads(route.calls[0].request.content)
        assert "parityCheck { pause }" in sent["query"]

    @respx.mock
    async def test_resume_parity_check_uses_grouped_field(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"parityCheck": {"resume": True}}})
        )
        await client.resume_parity_check()
        sent = json.loads(route.calls[0].request.content)
        assert "parityCheck { resume }" in sent["query"]

    @respx.mock
    async def test_cancel_parity_check_uses_grouped_field(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"parityCheck": {"cancel": True}}})
        )
        await client.cancel_parity_check()
        sent = json.loads(route.calls[0].request.content)
        assert "parityCheck { cancel }" in sent["query"]


class TestVmMutations:
    @respx.mock
    async def test_start_vm_normalises_boolean_payload(self, client):
        # Drift #60: VM mutations return ``Boolean!`` on Unraid API 4.32+.
        # The client flattens to ``{"ok": bool, "id": vm_id}``.
        route = respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"vm": {"start": True}}}))
        result = await client.start_vm("u1")
        assert result == {"ok": True, "id": "u1"}
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"id": "u1"}
        assert "$id: PrefixedID!" in sent["query"]
        # No selection set on the boolean response.
        assert "uuid" not in sent["query"]
        assert "{ start(id: $id) }" in sent["query"]

    @respx.mock
    async def test_stop_vm_returns_false_when_server_says_false(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"vm": {"stop": False}}}))
        result = await client.stop_vm("u1")
        assert result == {"ok": False, "id": "u1"}

    @respx.mock
    async def test_force_stop_vm_uses_force_stop_field_name(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"vm": {"forceStop": True}}})
        )
        result = await client.force_stop_vm("u1")
        assert result == {"ok": True, "id": "u1"}
        sent = json.loads(route.calls[0].request.content)
        assert "forceStop(id: $id)" in sent["query"]

    @respx.mock
    async def test_vm_mutate_raises_when_action_field_missing(self, client):
        # Drift #181: a missing action field used to be silently coerced to ok=False,
        # masking schema drift as a routine refusal.
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"vm": {}}}))
        with pytest.raises(UnraidError, match=r"missing vm\.start"):
            await client.start_vm("u1")

    @respx.mock
    async def test_vm_mutate_raises_when_vm_block_missing(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"vm": None}}))
        with pytest.raises(UnraidError, match=r"missing vm\.stop"):
            await client.stop_vm("u1")

    @respx.mock
    async def test_vm_mutate_raises_on_non_bool_payload(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"vm": {"pause": "yes"}}}))
        with pytest.raises(UnraidError, match=r"non-bool result"):
            await client.pause_vm("u1")


class TestNotificationMutations:
    @respx.mock
    async def test_archive_notification_passes_prefixed_id(self, client):
        # Drift #61/#176: ``ID!`` became ``PrefixedID!`` and the mutation
        # now returns the archived ``Notification`` (not the legacy
        # ``NotificationOverview`` counters).
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "archiveNotification": {
                            "id": "n1",
                            "type": "ARCHIVE",
                            "title": "test",
                            "importance": "INFO",
                            "timestamp": "2026-05-16T12:00:00Z",
                        },
                    },
                },
            )
        )
        await client.archive_notification("n1")
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"id": "n1"}
        assert "$id: PrefixedID!" in sent["query"]
        assert "id type title importance timestamp" in sent["query"]

    @respx.mock
    async def test_delete_notification_requires_type_argument(self, client):
        # Drift #61: the live schema requires a ``type: NotificationType!``
        # argument so it knows which counter to decrement.
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "deleteNotification": {
                            "unread": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                            "archive": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                        },
                    },
                },
            )
        )
        await client.delete_notification("n1")
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"id": "n1", "type": "UNREAD"}
        assert "$id: PrefixedID!" in sent["query"]
        assert "$type: NotificationType!" in sent["query"]

    @respx.mock
    async def test_delete_notification_forwards_archive_type(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "deleteNotification": {
                            "unread": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                            "archive": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                        },
                    },
                },
            )
        )
        await client.delete_notification("n1", notification_type="ARCHIVE")
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"id": "n1", "type": "ARCHIVE"}

    @respx.mock
    async def test_archive_all_lists_then_bulk_archives(self, client):
        # Drift #176: ``archiveAll(importance)`` was removed; the
        # replacement is ``archiveNotifications(ids: [PrefixedID!]!)``.
        # Importance-filtering moved client-side — the method now lists
        # unread, applies the filter, and bulk-archives the matched IDs.
        notifs = [
            {"id": "n_info", "type": "UNREAD", "title": "info", "importance": "INFO"},
            {"id": "n_warn", "type": "UNREAD", "title": "warn", "importance": "WARNING"},
            {"id": "n_alert", "type": "UNREAD", "title": "alert", "importance": "ALERT"},
        ]
        route = respx.post(GRAPHQL_URL).mock(
            side_effect=[
                httpx.Response(200, json={"data": {"notifications": {"id": "wrap", "list": notifs}}}),
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "archiveNotifications": {
                                "unread": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                                "archive": {"total": 3, "info": 1, "warning": 1, "alert": 1},
                            },
                        },
                    },
                ),
            ]
        )
        await client.archive_all_notifications()
        # First call lists unread; second call archives every collected id.
        list_call = json.loads(route.calls[0].request.content)
        assert list_call["variables"]["type"] == "UNREAD"
        archive_call = json.loads(route.calls[1].request.content)
        assert archive_call["variables"] == {"ids": ["n_info", "n_warn", "n_alert"]}
        assert "$ids: [PrefixedID!]!" in archive_call["query"]

    @respx.mock
    async def test_archive_all_filters_by_importance_client_side(self, client):
        notifs = [
            {"id": "n_info", "type": "UNREAD", "title": "info", "importance": "INFO"},
            {"id": "n_warn", "type": "UNREAD", "title": "warn", "importance": "WARNING"},
            {"id": "n_alert", "type": "UNREAD", "title": "alert", "importance": "ALERT"},
        ]
        route = respx.post(GRAPHQL_URL).mock(
            side_effect=[
                httpx.Response(200, json={"data": {"notifications": {"id": "wrap", "list": notifs}}}),
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "archiveNotifications": {
                                "unread": {"total": 2, "info": 1, "warning": 0, "alert": 1},
                                "archive": {"total": 1, "info": 0, "warning": 1, "alert": 0},
                            },
                        },
                    },
                ),
            ]
        )
        await client.archive_all_notifications(importance="WARNING")
        archive_call = json.loads(route.calls[1].request.content)
        assert archive_call["variables"] == {"ids": ["n_warn"]}

    @respx.mock
    async def test_archive_all_short_circuits_when_inbox_empty(self, client):
        # Empty match -> no mutation call, no-op response shape.
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"notifications": {"id": "wrap", "list": []}}}),
        )
        result = await client.archive_all_notifications(importance="ALERT")
        assert result == {"unread": None, "archive": None}


class TestNotificationLiteralRoundTrip:
    """Happy-path coverage for every accepted ``NotificationType`` /
    ``NotificationImportance`` literal value (#165).

    Confirms the tightened ``Literal`` type aliases on the client
    methods don't regress runtime behaviour for any valid value.
    """

    @respx.mock
    @pytest.mark.parametrize("ntype", ["UNREAD", "ARCHIVE"])
    async def test_list_notifications_accepts_every_type(self, client, ntype):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"notifications": {"id": "wrap", "list": []}}}),
        )
        await client.list_notifications(notification_type=ntype)
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"]["type"] == ntype

    @respx.mock
    @pytest.mark.parametrize("ntype", ["UNREAD", "ARCHIVE"])
    async def test_delete_notification_accepts_every_type(self, client, ntype):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "deleteNotification": {
                            "unread": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                            "archive": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                        },
                    },
                },
            )
        )
        await client.delete_notification("n1", notification_type=ntype)
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"id": "n1", "type": ntype}

    @respx.mock
    @pytest.mark.parametrize("importance", ["INFO", "WARNING", "ALERT"])
    async def test_archive_all_accepts_every_importance(self, client, importance):
        # Importance is applied client-side post-#176, so an empty list
        # response shows every literal value is accepted without raising.
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"notifications": {"id": "wrap", "list": []}}}),
        )
        result = await client.archive_all_notifications(importance=importance)
        assert result == {"unread": None, "archive": None}


class TestGetMe:
    @respx.mock
    async def test_get_me_returns_user_model(self, client):
        me = {"id": "u1", "name": "root", "description": "admin", "roles": ["ADMIN"]}
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"me": me}}))
        result = await client.get_me()
        assert result.name == "root"
        assert result.roles == ["ADMIN"]

    @respx.mock
    async def test_get_me_raises_on_missing_top_level_field(self, client):
        # Regression for #65: missing key is schema-drift, not "no user".
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {}}))
        with pytest.raises(UnraidError, match="Missing 'me'"):
            await client.get_me()

    @respx.mock
    async def test_get_me_query_does_not_request_password(self, client):
        # Regression for #107: never select UserAccount.password — it returns
        # the /etc/shadow hash and would land in MCP transcripts and logs.
        # Word-boundary regex so a future legitimate `passwordExpiry` field
        # would not falsely flag this assertion (#132).
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"me": {"id": "u1", "name": "root"}}}),
        )
        await client.get_me()
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
        instance = User.model_validate({"id": "u1", "name": "root", "roles": ["ADMIN"], "password": "$6$shadow_hash"})
        assert "password" not in instance.model_dump()
        assert not hasattr(instance, "password")
        assert instance.model_extra == {} or instance.model_extra is None

    @respx.mock
    async def test_get_me_strips_server_pushed_password_end_to_end(self, client):
        # Regression for #132: simulate the Unraid API pushing `password`
        # unsolicited and assert it does not appear in the model_dump of
        # the value `unraid_get_me` returns to FastMCP.
        me = {"id": "u1", "name": "root", "roles": ["ADMIN"], "password": "$6$shadow_hash"}
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"me": me}}))
        result = await client.get_me()
        assert "password" not in result.model_dump()


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


# Validation-failure response shape — matches what the live Unraid server
# emits when a query references a non-existent field. The error code is
# what `_check_graphql_errors` keys on to raise `UnraidValidationError`,
# which the singular-query client methods catch to drive the list-fallback.
_VALIDATION_ERROR_BODY = {
    "errors": [
        {
            "message": "Cannot query field on type",
            "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"},
        },
    ],
}


class TestGetDisk:
    @respx.mock
    async def test_singular_query_happy_path(self, client):
        # Unraid API 4.32+ exposes ``Query.disk(id: PrefixedID!)`` — one
        # round trip, no list scan.
        disk = {"id": "d1", "name": "disk1", "smartStatus": "PASS"}
        route = respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"disk": disk}}))
        result = await client.get_disk("d1")
        assert result.id == "d1"
        assert result.name == "disk1"
        assert route.call_count == 1
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"id": "d1"}
        assert "$id: PrefixedID!" in sent["query"]
        assert "disk(id: $id)" in sent["query"]

    @respx.mock
    async def test_falls_back_to_list_on_validation_error(self, client):
        # Older schemas without ``Query.disk`` raise
        # ``GRAPHQL_VALIDATION_FAILED``; the client retries via the list
        # query so the singular helper still works on old servers.
        disks = [{"id": "d1", "name": "disk1"}, {"id": "d2", "name": "disk2"}]
        responses = iter(
            [
                httpx.Response(200, json={"data": None, **_VALIDATION_ERROR_BODY}),
                httpx.Response(200, json={"data": {"disks": disks}}),
            ],
        )
        route = respx.post(GRAPHQL_URL).mock(side_effect=lambda _request: next(responses))
        result = await client.get_disk("d2")
        assert result.id == "d2"
        assert route.call_count == 2

    @respx.mock
    async def test_falls_back_to_list_when_singular_returns_null(self, client):
        # ``Query.disk`` is nullable on the schema — a present-but-null
        # response means the server has no disk matching the id. Fall back
        # to the list path so callers can still pass ``Disk.name`` as the
        # identifier (the legacy lookup matched on both).
        disks = [{"id": "d1", "name": "disk1"}]
        responses = iter(
            [
                httpx.Response(200, json={"data": {"disk": None}}),
                httpx.Response(200, json={"data": {"disks": disks}}),
            ],
        )
        respx.post(GRAPHQL_URL).mock(side_effect=lambda _request: next(responses))
        result = await client.get_disk("disk1")
        assert result.id == "d1"

    @respx.mock
    async def test_not_found_raises_unraid_not_found(self, client):
        # Singular path returns null and the list does not contain the
        # requested id — both legs miss, so `UnraidNotFoundError` propagates.
        responses = iter(
            [
                httpx.Response(200, json={"data": {"disk": None}}),
                httpx.Response(200, json={"data": {"disks": [{"id": "d1", "name": "disk1"}]}}),
            ],
        )
        respx.post(GRAPHQL_URL).mock(side_effect=lambda _request: next(responses))
        with pytest.raises(UnraidNotFoundError, match="Disk with id 'nope' not found"):
            await client.get_disk("nope")


class TestGetContainer:
    @respx.mock
    async def test_singular_query_happy_path(self, client):
        # Unraid API 4.32+ exposes ``Docker.container(id: PrefixedID!)``
        # under the grouped ``docker`` root — one round trip.
        container = {"id": "abc", "names": ["/plex"], "state": "running"}
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"docker": {"container": container}}}),
        )
        result = await client.get_container("abc")
        assert result.id == "abc"
        assert result.names == ["/plex"]
        assert route.call_count == 1
        sent = json.loads(route.calls[0].request.content)
        assert sent["variables"] == {"id": "abc"}
        assert "$id: PrefixedID!" in sent["query"]
        assert "container(id: $id)" in sent["query"]

    @respx.mock
    async def test_falls_back_to_list_on_validation_error(self, client):
        containers = [{"id": "abc", "names": ["/plex"]}, {"id": "def", "names": ["/sonarr"]}]
        responses = iter(
            [
                httpx.Response(200, json={"data": None, **_VALIDATION_ERROR_BODY}),
                httpx.Response(200, json={"data": {"docker": {"containers": containers}}}),
            ],
        )
        route = respx.post(GRAPHQL_URL).mock(side_effect=lambda _request: next(responses))
        result = await client.get_container("def")
        assert result.id == "def"
        assert route.call_count == 2

    @respx.mock
    async def test_falls_back_to_list_when_singular_returns_null(self, client):
        # ``Docker.container`` returns null when the daemon has no container
        # by that id; the fallback also matches by name so callers can pass
        # either identifier.
        containers = [{"id": "abc", "names": ["/plex"]}]
        responses = iter(
            [
                httpx.Response(200, json={"data": {"docker": {"container": None}}}),
                httpx.Response(200, json={"data": {"docker": {"containers": containers}}}),
            ],
        )
        respx.post(GRAPHQL_URL).mock(side_effect=lambda _request: next(responses))
        result = await client.get_container("plex")
        assert result.id == "abc"

    @respx.mock
    async def test_not_found_raises_unraid_not_found(self, client):
        responses = iter(
            [
                httpx.Response(200, json={"data": {"docker": {"container": None}}}),
                httpx.Response(200, json={"data": {"docker": {"containers": [{"id": "abc", "names": ["/plex"]}]}}}),
            ],
        )
        respx.post(GRAPHQL_URL).mock(side_effect=lambda _request: next(responses))
        with pytest.raises(UnraidNotFoundError, match="Container 'nope' not found"):
            await client.get_container("nope")


class TestGetShare:
    @respx.mock
    async def test_lookup_by_name_returns_share(self, client):
        # No singular share query exists on the Unraid schema — the client
        # always lists and filters, but encapsulates the scan so the tool
        # layer keeps a single call site.
        shares = [{"name": "media"}, {"name": "backups"}]
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"shares": shares}}))
        result = await client.get_share("backups")
        assert result.name == "backups"

    @respx.mock
    async def test_miss_raises_unraid_not_found(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"shares": [{"name": "media"}]}}),
        )
        with pytest.raises(UnraidNotFoundError, match="Share 'nope' not found"):
            await client.get_share("nope")
