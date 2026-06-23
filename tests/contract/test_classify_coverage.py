"""Offline self-test for the root-field coverage ratchet (#241).

``classify_coverage`` partitions one root type's coverage state into the
three arms the ratchet asserts on. The live ``test_root_coverage`` tests only
exercise the happy path against the pinned snapshot, so a refactor that broke
the comparison could silently let a regressing field through. These unit tests
feed synthetic inputs and lock in that each guard still fires.
"""

from __future__ import annotations

from tests.contract._surface import classify_coverage


def test_clean_state_has_no_violations() -> None:
    violations = classify_coverage(
        schema_fields={"covered", "declined"},
        invoked={"covered"},
        declined={"declined"},
    )
    assert violations.unaccounted == []
    assert violations.now_covered == []
    assert violations.phantom == []


def test_uncovered_and_undeclined_field_is_unaccounted() -> None:
    violations = classify_coverage(
        schema_fields={"covered", "orphan"},
        invoked={"covered"},
        declined=set(),
    )
    assert violations.unaccounted == ["orphan"]
    assert violations.now_covered == []
    assert violations.phantom == []


def test_declined_but_now_covered_field_is_stale() -> None:
    violations = classify_coverage(
        schema_fields={"wasDeclined"},
        invoked={"wasDeclined"},
        declined={"wasDeclined"},
    )
    assert violations.now_covered == ["wasDeclined"]
    assert violations.unaccounted == []
    assert violations.phantom == []


def test_declined_field_absent_from_schema_is_phantom() -> None:
    violations = classify_coverage(
        schema_fields={"real"},
        invoked={"real"},
        declined={"vanished"},
    )
    assert violations.phantom == ["vanished"]
    assert violations.unaccounted == []
    assert violations.now_covered == []


def test_violations_are_sorted() -> None:
    violations = classify_coverage(
        schema_fields={"zeta", "alpha"},
        invoked=set(),
        declined=set(),
    )
    assert violations.unaccounted == ["alpha", "zeta"]
