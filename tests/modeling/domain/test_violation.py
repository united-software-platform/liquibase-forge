"""Нарушение модели: вложение путей и исключение со списком нарушений."""

from __future__ import annotations

import pytest

from forge.modeling.domain.violation import ModelViolationError, Violation, join_path


@pytest.mark.parametrize(
    ("prefix", "path", "expected"),
    [
        ("columns[1]", "length", "columns[1].length"),
        ("tables[0]", "columns[1].length", "tables[0].columns[1].length"),
        ("tables[0]", "primary_key[1]", "tables[0].primary_key[1]"),
        ("primary_key", "[1]", "primary_key[1]"),
        ("tables[2]", "", "tables[2]"),
        ("", "version", "version"),
    ],
)
def test_join_path(prefix: str, path: str, expected: str) -> None:
    assert join_path(prefix, path) == expected


def test_violation_under_keeps_code_and_message() -> None:
    violation = Violation("length", "missing_type_parameter", "нет length")

    assert violation.under("columns[1]") == Violation(
        "columns[1].length", "missing_type_parameter", "нет length"
    )


def test_error_under_prefixes_every_violation_in_order() -> None:
    error = ModelViolationError(
        [Violation("name", "invalid_identifier", "a"), Violation("length", "unknown_type", "b")]
    )

    nested = error.under("columns[0]").under("tables[3]")

    assert [v.path for v in nested.violations] == [
        "tables[3].columns[0].name",
        "tables[3].columns[0].length",
    ]


def test_error_requires_violations() -> None:
    with pytest.raises(ValueError):
        ModelViolationError([])
