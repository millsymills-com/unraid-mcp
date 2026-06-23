"""Root-field coverage ratchet against the pinned snapshot.

Every ``Query``/``Mutation``/``Subscription`` root field in
``tests/contract/snapshot.graphql`` must be either:

  - **covered** — invoked as a top-level selection by some ``QUERY_*``/
    ``MUTATION_*`` operation constant in ``clients/unraid.py`` (the client
    method a tool calls), or
  - **explicitly declined** — listed in :data:`INTENTIONALLY_UNCOVERED`
    with a rationale.

A new root field that is neither fails the build, forcing a deliberate
choice: add a tool or record why it is out of scope. The registry is also
checked for rot — an entry that became covered, or that no longer exists in
the schema, fails too. Keep ``docs/coverage-matrix.md`` in step with changes
here. Runs in default pytest — no live env needed.
"""

from __future__ import annotations

import pytest

from tests.contract._surface import (
    SNAPSHOT_PATH,
    classify_coverage,
    invoked_root_fields,
    root_field_names,
)

pytestmark = pytest.mark.contract

# Root fields we deliberately do not expose as tools, grouped by rationale.
# Keyed by root type because a name can mean different things per root
# (e.g. Query.apiKey is a lookup; Mutation.apiKey is a mutation namespace).
INTENTIONALLY_UNCOVERED: dict[str, dict[str, frozenset[str]]] = {
    "Query": {
        "api keys & permissions — admin auth surface, not agent-operable": frozenset(
            {
                "apiKey",
                "apiKeys",
                "apiKeyPossiblePermissions",
                "apiKeyPossibleRoles",
                "getApiKeyCreationFormSchema",
                "getAvailableAuthActions",
                "getPermissionsForRoles",
                "previewEffectivePermissions",
            }
        ),
        "OIDC / SSO — admin provider config carries clientSecret (snapshot L2711)": frozenset(
            {
                "oidcConfiguration",
                "oidcProvider",
                "oidcProviders",
                "validateOidcSession",
            }
        ),
        "config, settings & display — install-time configuration": frozenset(
            {
                "config",
                "customization",
                "publicTheme",
                "isFreshInstall",
            }
        ),
        "identity & multi-server inventory": frozenset(
            {
                "online",
                "owner",
                "internalBootContext",
                "server",
                "servers",
            }
        ),
    },
    "Mutation": {
        "notification lifecycle beyond archive/delete": frozenset(
            {
                "createNotification",
                "notifyIfUnique",
                "unreadNotification",
                "unarchiveNotifications",
                "unarchiveAll",
                "archiveAll",
                "deleteArchivedNotifications",
                "recalculateOverview",
            }
        ),
        "Docker organizer / template management (UI bookkeeping)": frozenset(
            {
                "createDockerFolder",
                "createDockerFolderWithItems",
                "setDockerFolderChildren",
                "deleteDockerEntries",
                "moveDockerEntriesToFolder",
                "moveDockerItemsToPosition",
                "renameDockerFolder",
                "updateDockerViewPreferences",
                "syncDockerTemplatePaths",
                "resetDockerTemplateMappings",
                "refreshDockerDigests",
            }
        ),
        "settings & system configuration mutations": frozenset(
            {
                "updateServerIdentity",
                "updateSshSettings",
                "updateSettings",
                "updateApiSettings",
                "updateSystemTime",
                "updateTemperatureConfig",
            }
        ),
        "plugin install/remove": frozenset({"addPlugin", "removePlugin"}),
        "UPS configuration": frozenset({"configureUps"}),
        "Connect / cloud / remote-access setup": frozenset(
            {
                "connectSignIn",
                "connectSignOut",
                "setupRemoteAccess",
                "enableDynamicRemoteAccess",
                "initiateFlashBackup",
            }
        ),
        "mutation namespaces not implemented": frozenset(
            {
                "apiKey",
                "customization",
                "rclone",
                "onboarding",
                "unraidPlugins",
            }
        ),
    },
    "Subscription": {
        "subscriptions — transport is request/response only": frozenset(
            {
                "arraySubscription",
                "displaySubscription",
                "dockerContainerStats",
                "logFile",
                "notificationAdded",
                "notificationsOverview",
                "notificationsWarningsAndAlerts",
                "ownerSubscription",
                "parityHistorySubscription",
                "pluginInstallUpdates",
                "serversSubscription",
                "systemMetricsCpu",
                "systemMetricsCpuTelemetry",
                "systemMetricsMemory",
                "systemMetricsTemperature",
                "upsUpdates",
            }
        ),
    },
}


def _declined(root_label: str) -> set[str]:
    """Flattened registry for one root type."""
    return set().union(*INTENTIONALLY_UNCOVERED[root_label].values())


@pytest.fixture(scope="module")
def snapshot_roots() -> dict[str, set[str]]:
    return root_field_names(SNAPSHOT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def invoked() -> dict[str, set[str]]:
    return invoked_root_fields()


@pytest.mark.parametrize("root_label", ["Query", "Mutation", "Subscription"])
def test_no_unaccounted_root_fields(
    root_label: str, snapshot_roots: dict[str, set[str]], invoked: dict[str, set[str]]
) -> None:
    """Every root field is covered by a tool or explicitly declined."""
    unaccounted = classify_coverage(snapshot_roots[root_label], invoked[root_label], _declined(root_label)).unaccounted

    assert not unaccounted, (
        f"{len(unaccounted)} new {root_label} root field(s) have no tool and no "
        f"'won't cover' entry: {unaccounted}.\n"
        "Either add a tool in src/unraid_mcp/tools/ (and a client operation), or "
        f"record them under INTENTIONALLY_UNCOVERED['{root_label}'] in this file "
        "with a rationale. Update docs/coverage-matrix.md to match."
    )


@pytest.mark.parametrize("root_label", ["Query", "Mutation", "Subscription"])
def test_registry_has_no_stale_entries(
    root_label: str, snapshot_roots: dict[str, set[str]], invoked: dict[str, set[str]]
) -> None:
    """Declined entries must still exist and must still be uncovered."""
    violations = classify_coverage(snapshot_roots[root_label], invoked[root_label], _declined(root_label))

    assert not violations.now_covered, (
        f"{root_label} field(s) {violations.now_covered} are listed as intentionally "
        "uncovered but a tool now invokes them. Remove them from INTENTIONALLY_UNCOVERED."
    )

    assert not violations.phantom, (
        f"{root_label} field(s) {violations.phantom} are listed as intentionally "
        "uncovered but no longer exist in the snapshot. Drop them from "
        "INTENTIONALLY_UNCOVERED."
    )


def test_registry_groups_are_disjoint() -> None:
    """No field is listed under two rationale groups within a root type."""
    overlaps: list[str] = []
    for root_label, groups in INTENTIONALLY_UNCOVERED.items():
        seen: set[str] = set()
        for members in groups.values():
            overlaps.extend(f"{root_label}.{name}" for name in members & seen)
            seen |= members
    assert not overlaps, f"Duplicate registry entries: {sorted(overlaps)}"
