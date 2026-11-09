"""Offline regression tests for live-write notification teardown.

``delete_notification_any_state`` runs only in the live_write tier, which never
runs in CI, so its orphan detection has no live signal to protect it. The helper
deletes a fixture notification from a bin it cannot observe in advance (UNREAD
or ARCHIVE) and must then decide whether the fixture leaked. These tests drive
it against a fake client that models both plausible API behaviours for a delete
aimed at the wrong bin — raising, and succeeding as a no-op — and pin that the
leak verdict comes from the notification's end state rather than from how many
mutations happened to fail.

The helper lives in ``tests.live_write._teardown`` — a fixture-free module — so
importing it here does not activate the live suite's session-scoped autouse gate
(which would otherwise skip this whole file).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client

from tests.live_write import _teardown
from tests.live_write._teardown import PAGE_SIZE, delete_notification_any_state, select_mcptest_orphans
from unraid_mcp.errors import UnraidError, UnraidNotFoundError
from unraid_mcp.models.notifications import Notification
from unraid_mcp.server import create_server

if TYPE_CHECKING:
    from collections.abc import Callable

    from unraid_mcp.models.notifications import NotificationType

_NID = "mcptest_leak_1700000000"


class _FakeClient:
    """Stand-in for ``UnraidClient`` holding two in-memory notification bins."""

    def __init__(
        self,
        *,
        unread: list[str] | None = None,
        archive: list[str] | None = None,
        delete_errors: dict[str, Exception] | None = None,
        deletes_remove: bool = True,
        list_error: Exception | None = None,
    ) -> None:
        self.bins: dict[str, list[str]] = {"UNREAD": list(unread or []), "ARCHIVE": list(archive or [])}
        self.delete_errors = delete_errors or {}
        self.deletes_remove = deletes_remove
        self.list_error = list_error
        self.deleted_types: list[str] = []
        self.listed_types: list[str] = []
        self.list_pages: list[tuple[str, int, int]] = []
        self.closed = False

    async def mutate(self, _query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        args = variables or {}
        ntype = str(args["type"])
        self.deleted_types.append(ntype)
        error = self.delete_errors.get(ntype)
        if error is not None:
            raise error
        if self.deletes_remove and args["id"] in self.bins[ntype]:
            self.bins[ntype].remove(str(args["id"]))
        return {"deleteNotification": True}

    async def list_notifications(
        self,
        notification_type: NotificationType = "UNREAD",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        if self.list_error is not None:
            raise self.list_error
        self.listed_types.append(notification_type)
        self.list_pages.append((notification_type, limit, offset))
        return [Notification(id=nid) for nid in self.bins[notification_type][offset : offset + limit]]

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def install_client(monkeypatch: pytest.MonkeyPatch) -> Callable[[_FakeClient], _FakeClient]:
    """Make ``delete_notification_any_state`` build the supplied fake client."""

    def _install(client: _FakeClient) -> _FakeClient:
        monkeypatch.setattr(_teardown, "build_raw_client", lambda: client)
        return client

    return _install


async def test_already_deleted_notification_is_not_an_orphan(
    install_client: Callable[[_FakeClient], _FakeClient],
) -> None:
    """The delete test removes the fixture itself; teardown must not cry orphan.

    Both bin-targeted deletes hit an absent id and fail, yet nothing leaked — a
    failure count of two says nothing about the end state.
    """
    absent = UnraidNotFoundError("no such notification")
    client = install_client(_FakeClient(delete_errors={"ARCHIVE": absent, "UNREAD": absent}))

    await delete_notification_any_state(_NID)

    assert client.closed


async def test_single_real_failure_is_not_swallowed(install_client: Callable[[_FakeClient], _FakeClient]) -> None:
    """A wrong-bin delete that no-ops must not mask a genuine failure.

    ARCHIVE succeeds as a no-op, UNREAD fails for real and the entry stays put:
    one failure, but a real orphan.
    """
    install_client(_FakeClient(unread=[_NID], delete_errors={"UNREAD": UnraidError("server error")}))

    with pytest.raises(ExceptionGroup) as excinfo:
        await delete_notification_any_state(_NID)

    assert "still present" in str(excinfo.value)
    assert [type(exc) for exc in excinfo.value.exceptions] == [UnraidError]


async def test_both_delete_failures_reach_the_report(install_client: Callable[[_FakeClient], _FakeClient]) -> None:
    """Both causes must survive — the ARCHIVE error alone is the benign one."""
    unread_error = UnraidError("real unread failure")
    install_client(
        _FakeClient(
            unread=[_NID],
            delete_errors={"ARCHIVE": UnraidNotFoundError("wrong bin"), "UNREAD": unread_error},
        )
    )

    with pytest.raises(ExceptionGroup) as excinfo:
        await delete_notification_any_state(_NID)

    assert unread_error in excinfo.value.exceptions
    assert len(excinfo.value.exceptions) == 2


async def test_orphan_in_archive_bin_is_detected(install_client: Callable[[_FakeClient], _FakeClient]) -> None:
    """Both deletes report success but the entry survives in the archive bin."""
    client = install_client(_FakeClient(archive=[_NID], deletes_remove=False))

    with pytest.raises(RuntimeError, match="still present"):
        await delete_notification_any_state(_NID)

    assert sorted(client.listed_types) == ["ARCHIVE", "UNREAD"]


async def test_orphan_past_the_first_page_is_detected(
    install_client: Callable[[_FakeClient], _FakeClient],
) -> None:
    """A deep archive bin must be paged through, not sampled.

    The bin is unsorted, so a surviving fixture can sit behind hundreds of
    unrelated entries the archive tests accumulated.
    """
    deep_bin = [f"unrelated_{i}" for i in range(PAGE_SIZE)] + [_NID]
    client = install_client(_FakeClient(archive=deep_bin, deletes_remove=False))

    with pytest.raises(RuntimeError, match="still present"):
        await delete_notification_any_state(_NID)

    assert ("ARCHIVE", PAGE_SIZE, PAGE_SIZE) in client.list_pages


async def test_paging_stops_at_a_short_page(install_client: Callable[[_FakeClient], _FakeClient]) -> None:
    """A bin shorter than one page costs exactly one request."""
    client = install_client(_FakeClient(unread=[_NID], delete_errors={"ARCHIVE": UnraidNotFoundError("wrong bin")}))

    await delete_notification_any_state(_NID)

    assert sorted(client.list_pages) == [("ARCHIVE", PAGE_SIZE, 0), ("UNREAD", PAGE_SIZE, 0)]


async def test_unverifiable_end_state_is_surfaced(install_client: Callable[[_FakeClient], _FakeClient]) -> None:
    """If the read-back itself fails, teardown cannot claim success."""
    install_client(_FakeClient(list_error=UnraidError("connection reset")))

    with pytest.raises(ExceptionGroup, match="could not verify"):
        await delete_notification_any_state(_NID)


async def test_successful_delete_is_silent(install_client: Callable[[_FakeClient], _FakeClient]) -> None:
    """Happy path: the wrong-bin attempt fails, the right one removes the entry."""
    client = install_client(_FakeClient(unread=[_NID], delete_errors={"ARCHIVE": UnraidNotFoundError("wrong bin")}))

    await delete_notification_any_state(_NID)

    assert sorted(client.deleted_types) == ["ARCHIVE", "UNREAD"]
    assert client.bins["UNREAD"] == []


async def test_client_is_closed_when_teardown_raises(install_client: Callable[[_FakeClient], _FakeClient]) -> None:
    """A raised orphan report must not also leak the httpx client."""
    client = install_client(_FakeClient(unread=[_NID], delete_errors={"UNREAD": UnraidError("server error")}))

    with pytest.raises(ExceptionGroup):
        await delete_notification_any_state(_NID)

    assert client.closed


class TestSelectMcptestOrphans:
    """The session-end backstop's filter over one notification listing."""

    def test_reads_the_result_envelope(self) -> None:
        entry = {"title": "mcptest_leak", "id": _NID}

        assert select_mcptest_orphans({"result": [entry]}) == [entry]

    def test_drops_foreign_notifications(self) -> None:
        payload = {"result": [{"title": "Array started"}, {"title": "mcptest_leak"}, {"title": "prod-mcptest-db"}]}

        assert select_mcptest_orphans(payload) == [{"title": "mcptest_leak"}]

    def test_matches_case_insensitively(self) -> None:
        assert select_mcptest_orphans({"result": [{"title": "MCPTEST_Leak"}]}) == [{"title": "MCPTEST_Leak"}]

    @pytest.mark.parametrize(
        "payload",
        [None, "not a listing", {}, {"result": None}, [{"title": "mcptest_leak"}]],
    )
    def test_unrecognized_payloads_yield_nothing(self, payload: object) -> None:
        assert select_mcptest_orphans(payload) == []

    def test_entry_without_a_title_is_not_an_orphan(self) -> None:
        assert select_mcptest_orphans({"result": [{"id": _NID, "title": None}, 42]}) == []


async def test_orphan_scan_reads_the_live_payload_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ``structured_content`` shape the session-end scan parses.

    The scan is the last line of defence and reports nothing when it cannot
    recognize the payload, so a FastMCP change to the envelope has to fail here
    rather than on the tower.
    """
    mock_client = AsyncMock()
    mock_client.validate_connection.return_value = None
    mock_client.list_notifications.return_value = [Notification(id=_NID, title="mcptest_leak")]
    monkeypatch.setenv("UNRAID_API_KEY", "test-key")
    monkeypatch.setenv("UNRAID_MODE", "readwrite")
    monkeypatch.setattr("unraid_mcp.clients.unraid.UnraidClient", lambda *_a, **_kw: mock_client)

    async with Client(create_server()) as client:
        listing = await client.call_tool(
            "unraid_list_notifications", {"notification_type": "ARCHIVE", "limit": PAGE_SIZE}
        )

    orphans = select_mcptest_orphans(listing.structured_content)
    assert [entry["id"] for entry in orphans] == [_NID]
    assert mock_client.list_notifications.await_args.kwargs["limit"] == PAGE_SIZE
