"""Fixture-free teardown helpers for the live-write suite.

Kept separate from ``conftest.py`` for the same reason as ``_gates.py``: offline
unit tests can import and exercise the teardown logic without importing the
conftest module, which would register its session-scoped autouse fixtures and
skip the whole run.
"""

from __future__ import annotations

from typing import cast

from tests.live_write._gates import MCPTEST_PREFIX
from unraid_mcp.clients.unraid import MUTATION_DELETE_NOTIFICATION, UnraidClient
from unraid_mcp.config import UnraidConfig, UnraidMode

NOTIFICATION_BINS = ("UNREAD", "ARCHIVE")
"""Both notification bins — a fixture can be orphaned in either one."""

PAGE_SIZE = 200
"""Entries per notification page. The archive bin grows with every session."""


def build_raw_client() -> UnraidClient:
    """A fresh raw GraphQL client for operations with no MCP tool (e.g. seeding)."""
    cfg = UnraidConfig(unraid_mode=UnraidMode.READWRITE)
    if cfg.unraid_api_key is None:
        raise RuntimeError("UNRAID_API_KEY must be set for live_write seeding")
    return UnraidClient(
        graphql_url=cfg.graphql_url,
        api_key=cfg.unraid_api_key,
        verify_ssl=cfg.unraid_verify_ssl,
        timeout=cfg.unraid_request_timeout,
        max_retries=cfg.unraid_max_retries,
    )


async def delete_notification_any_state(notification_id: str) -> None:
    """Delete from both unread and archive lists (state is unknown at teardown).

    At most one bin holds the notification — and the test may have deleted it
    already — so some of the two mutations are expected to be no-ops. The API is
    free to report a no-op either as success or as an error, which makes the
    number of failed mutations useless as a leak signal: two failures can mean
    the entry was already gone, and one failure can hide a real error. So the
    end state is read back instead, and the entry counts as orphaned only if a
    bin still holds it after both attempts.

    Args:
        notification_id: Id of the seeded notification to remove.

    Raises:
        ExceptionGroup: The entry is still present, or the read-back could not
            be performed. Carries every delete error collected along the way, so
            ``run_cleanup`` logs the real cause rather than whichever error came
            first.
        RuntimeError: The entry is still present although every mutation
            reported success.
    """
    client = build_raw_client()
    failures: list[Exception] = []
    try:
        for ntype in NOTIFICATION_BINS:
            try:
                await client.mutate(MUTATION_DELETE_NOTIFICATION, variables={"id": notification_id, "type": ntype})
            except Exception as exc:
                failures.append(exc)
        try:
            still_present = await _notification_present(client, notification_id)
        except Exception as exc:
            raise ExceptionGroup(
                f"could not verify deletion of notification {notification_id}",
                [*failures, exc],
            ) from None
        if still_present:
            msg = f"notification {notification_id} still present after ARCHIVE and UNREAD deletes"
            if failures:
                raise ExceptionGroup(msg, failures)
            raise RuntimeError(msg)
    finally:
        await client.close()


async def _notification_present(client: UnraidClient, notification_id: str) -> bool:
    """Whether either bin still holds ``notification_id``.

    Both bins are paged to the end rather than sampled: ``QUERY_NOTIFICATIONS``
    requests no sort order, so a surviving entry can sit anywhere in a bin that
    the archive tests keep growing.
    """
    for ntype in NOTIFICATION_BINS:
        offset = 0
        while True:
            entries = await client.list_notifications(notification_type=ntype, limit=PAGE_SIZE, offset=offset)
            if any(n.id == notification_id for n in entries):
                return True
            if len(entries) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
    return False


def select_mcptest_orphans(payload: object) -> list[dict[str, object]]:
    """Pick the ``mcptest_*`` entries out of one ``unraid_list_notifications`` result.

    The tool's ``structured_content`` wraps its list in a ``{"result": [...]}``
    envelope — pinned by ``test_orphan_scan_reads_the_live_payload_shape``,
    because an unrecognized payload silently empties the session-end backstop.

    Args:
        payload: Structured content from one ``unraid_list_notifications`` call.

    Returns:
        Entries whose title starts with the ``mcptest`` prefix, or an empty list
        when the payload holds no recognizable listing.
    """
    entries = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []
    return [
        cast("dict[str, object]", entry)
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("title", "")).lower().startswith(MCPTEST_PREFIX)
    ]
