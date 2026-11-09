"""Drift-format guard for the schema-probe workflow's fail-closed allowlist (#293).

The ``scrub`` step in ``.github/workflows/schema-probe.yml`` validates every
non-blank line of ``probe.log`` against two anchored regexes before any drift
content reaches the public issue or the step summary. Those regexes encode the
exact literal output of :func:`compute_schema_drift`, but neither file
references the other: change the drift message format and the allowlist
silently desyncs, after which the scrub rejects every genuine drift report and
the probe posts nothing.

These tests close that loop. They lift the scrub's shell fragments verbatim out
of the workflow and run them, so the patterns are exercised by a real shell
rather than by a Python transcription of them. The CI run on ``ubuntu-latest``
is the authoritative one — a local run uses whatever ``grep`` is on ``PATH``,
which is BSD grep on macOS rather than the GNU grep the workflow runner has.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from unraid_mcp.clients.unraid import SCHEMA_EXPECTATIONS, compute_schema_drift

if TYPE_CHECKING:
    from collections.abc import Iterable

BASH = "/bin/bash"
WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "schema-probe.yml"

# Assignment prefixes of the scrub fragments this guard replays. `unexpected=`
# carries the grep invocation itself, so a change to the alternation (dropping
# a pattern, adding a flag) is caught here rather than transcribed away.
SCRUB_PREFIXES = ("field_list=", "allow_missing=", "allow_type=", "unexpected=")


def _scrub_script() -> str:
    """Return the workflow's scrub fragments, verbatim and in file order, as shell source."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    fragments: list[tuple[int, str]] = []
    for prefix in SCRUB_PREFIXES:
        matches = [
            (m.start(), m.group(1)) for m in re.finditer(rf"^[ \t]*({re.escape(prefix)}.*)$", workflow, re.MULTILINE)
        ]
        assert len(matches) == 1, f"expected exactly one `{prefix}` line in {WORKFLOW.name}, found {len(matches)}"
        fragments.append(matches[0])
    # File order, not SCRUB_PREFIXES order: a workflow that defines a variable
    # after its use must fail this guard under `set -u`, not be quietly repaired.
    fragments.sort()
    body = "\n".join(text for _, text in fragments)
    # The step reads `content` from probe.log with blank lines stripped; the
    # harness supplies it on stdin instead. `set -euo pipefail` mirrors the step.
    return f"set -euo pipefail\ncontent=$(cat)\n{body}\nprintf '%s\\n' \"$unexpected\"\n"


def _scrub_rejects(lines: Iterable[str]) -> list[str]:
    """Return the subset of ``lines`` the workflow's fail-closed scrub would reject."""
    result = subprocess.run(
        [BASH, "-c", _scrub_script()],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    # A malformed pattern makes grep exit 2 with empty stdout, which `|| true`
    # swallows — without this the accept-everything tests would pass silently.
    assert not result.stderr, f"scrub emitted stderr: {result.stderr}"
    return [line for line in result.stdout.splitlines() if line]


def _every_shipped_drift_line() -> list[str]:
    """Every drift line the shipped client can emit for the real expectation set.

    Three probe results span the output space: no type present (type-missing
    branch for every type), every type present but empty (missing-fields branch
    with a full field list), and every type missing its alphabetically first
    field (missing-fields branch with a one-element list).
    """
    all_fields_gone: dict[str, set[str]] = {name: set() for name in SCHEMA_EXPECTATIONS}
    one_field_gone: dict[str, set[str]] = {
        name: set(sorted(fields)[1:]) for name, fields in SCHEMA_EXPECTATIONS.items()
    }
    return [
        *compute_schema_drift(SCHEMA_EXPECTATIONS, {}),
        *compute_schema_drift(SCHEMA_EXPECTATIONS, all_fields_gone),
        *compute_schema_drift(SCHEMA_EXPECTATIONS, one_field_gone),
    ]


class TestAllowlistAcceptsRealDrift:
    """The allowlist must accept every line the probe can legitimately publish."""

    def test_every_shipped_drift_line_passes_the_scrub(self) -> None:
        lines = _every_shipped_drift_line()
        assert lines, "SCHEMA_EXPECTATIONS yielded no drift lines — this guard would be vacuous"
        assert _scrub_rejects(lines) == []

    def test_corpus_covers_both_drift_formats(self) -> None:
        lines = _every_shipped_drift_line()
        assert any(": missing fields [" in line for line in lines)
        assert any(": type missing from server schema (client expects fields [" in line for line in lines)

    def test_empty_expected_field_set_passes_the_scrub(self) -> None:
        # `sorted(frozenset())` renders as `[]`, which only the type-missing
        # branch can emit — the missing-fields branch is guarded by `if missing:`.
        lines = compute_schema_drift({"Bare_9": frozenset()}, {})
        assert lines == ["Bare_9: type missing from server schema (client expects fields [])"]
        assert _scrub_rejects(lines) == []


class TestAllowlistRejectsEverythingElse:
    """Fail-closed: anything that is not an exact drift line must be withheld.

    Both formats need their own lookalikes. A loosened ``allow_type`` is
    invisible to a corpus of ``missing fields`` lines alone, because
    ``allow_missing`` rejects all of them on its own.
    """

    @pytest.mark.parametrize(
        "line",
        [
            pytest.param("Traceback (most recent call last):", id="traceback"),
            pytest.param("x-api-key: 0123456789abcdef", id="credential"),
            pytest.param("Disk: missing fields ['temp'] and more", id="trailing-text"),
            pytest.param("Disk: missing field(s) ['temp']", id="reworded-message"),
            pytest.param("Disk: missing fields temp", id="bare-field-name"),
            pytest.param("Disk: missing fields ['a','b']", id="repr-without-space"),
            pytest.param('Disk: missing fields ["temp"]', id="double-quoted-repr"),
            pytest.param("Disk-1: missing fields ['temp']", id="non-identifier-type"),
            pytest.param("  Disk: missing fields ['temp']", id="indented"),
        ],
    )
    def test_scrub_rejects_missing_fields_lookalikes(self, line: str) -> None:
        assert _scrub_rejects([line]) == [line]

    @pytest.mark.parametrize(
        "line",
        [
            pytest.param(
                "Disk: type missing from server schema (x-api-key: 0123456789abcdef)",
                id="injected-parenthetical",
            ),
            pytest.param(
                "Disk: type missing from server schema (client expects fields ['a']) and more",
                id="trailing-text",
            ),
            pytest.param("Disk: type missing (client expects fields ['a'])", id="reworded-message"),
            pytest.param("Disk: type missing from server schema (client expects fields a)", id="bare-field-name"),
            pytest.param(
                'Disk: type missing from server schema (client expects fields ["a"])',
                id="double-quoted-repr",
            ),
            pytest.param(
                "Disk-1: type missing from server schema (client expects fields ['a'])",
                id="non-identifier-type",
            ),
            pytest.param(
                "  Disk: type missing from server schema (client expects fields ['a'])",
                id="indented",
            ),
        ],
    )
    def test_scrub_rejects_type_missing_lookalikes(self, line: str) -> None:
        assert _scrub_rejects([line]) == [line]

    def test_one_bad_line_among_valid_ones_is_reported(self) -> None:
        valid = compute_schema_drift({"Disk": frozenset({"temp"})}, {"Disk": set()})
        assert _scrub_rejects([*valid, "Traceback (most recent call last):"]) == [
            "Traceback (most recent call last):",
        ]
