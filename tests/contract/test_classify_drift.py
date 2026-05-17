"""Offline tests for the schema-drift classifier (#179).

``_classify_drift`` partitions GraphQL schema differences into ``breaking``
and ``additive`` lists. The live drift test only exercises the no-drift path
in CI, so a regression that misclassifies field removals or type changes as
additive would silently let breaking drift through as ``xfail``. These
unit tests anchor each classification arm against hand-crafted schemas.
"""

from __future__ import annotations

from graphql import build_schema

from tests.contract.test_schema_drift import _classify_drift


def test_field_removal_is_breaking() -> None:
    old = build_schema("type Query { foo: String, bar: Int }")
    new = build_schema("type Query { foo: String }")
    breaking, additive = _classify_drift(old, new)
    assert any("field removed: Query.bar" in item for item in breaking)
    assert additive == []


def test_field_type_change_is_breaking() -> None:
    old = build_schema("type Query { foo: String, bar: Int }")
    new = build_schema("type Query { foo: Int, bar: Int }")
    breaking, _ = _classify_drift(old, new)
    assert any("Query.foo: String -> Int" in item for item in breaking)


def test_nullability_tightening_is_breaking() -> None:
    old = build_schema("type Query { foo: String }")
    new = build_schema("type Query { foo: String! }")
    breaking, _ = _classify_drift(old, new)
    assert any("Query.foo: String -> String!" in item for item in breaking)


def test_type_removal_is_breaking() -> None:
    old = build_schema("type Query { foo: Thing } type Thing { id: ID }")
    new = build_schema("type Query { foo: String }")
    breaking, _ = _classify_drift(old, new)
    assert any("type removed: Thing" in item for item in breaking)


def test_field_addition_is_additive() -> None:
    old = build_schema("type Query { foo: String }")
    new = build_schema("type Query { foo: String, bar: Int }")
    breaking, additive = _classify_drift(old, new)
    assert breaking == []
    assert any("field added: Query.bar" in item for item in additive)


def test_type_addition_is_additive() -> None:
    old = build_schema("type Query { foo: String }")
    new = build_schema("type Query { foo: String } type Extra { id: ID }")
    breaking, additive = _classify_drift(old, new)
    assert breaking == []
    assert any("type added: Extra" in item for item in additive)


def test_identical_schemas_have_no_drift() -> None:
    schema = build_schema("type Query { foo: String, bar: Int }")
    assert _classify_drift(schema, schema) == ([], [])


def test_mixed_breaking_and_additive() -> None:
    old = build_schema("type Query { foo: String, bar: Int }")
    new = build_schema("type Query { foo: String, baz: Boolean }")
    breaking, additive = _classify_drift(old, new)
    assert any("field removed: Query.bar" in item for item in breaking)
    assert any("field added: Query.baz" in item for item in additive)
