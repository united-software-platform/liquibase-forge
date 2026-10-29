"""Перевод определения CHECK в колонку и перечень: канонические формы PostgreSQL и отказы."""

from __future__ import annotations

import pytest

from forge.reconciliation.domain.actual_schema import ActualCheck, CheckValue
from forge.reconciliation.infrastructure.check_definition import parse_check


@pytest.mark.parametrize(
    ("definition", "column", "values"),
    [
        (
            "CHECK ((source = ANY (ARRAY['collector'::text, 'manual'::text])))",
            "source",
            {"collector", "manual"},
        ),
        (
            "CHECK (((source)::text = ANY ((ARRAY['collector'::character varying, "
            "'manual'::character varying])::text[])))",
            "source",
            {"collector", "manual"},
        ),
        ("CHECK ((priority = ANY (ARRAY[1, 2, 3])))", "priority", {1, 2, 3}),
        (
            "CHECK ((n = ANY (ARRAY[('-5'::integer)::bigint, (1)::bigint, '3000000000'::bigint])))",
            "n",
            {1, 3_000_000_000, -5},
        ),
        ("CHECK (((source)::text = 'collector'::text))", "source", {"collector"}),
        ("CHECK ((priority = 1))", "priority", {1}),
        (
            "CHECK ((source = ANY (ARRAY['o''clock'::text, 'a, b'::text, 'x = (y)'::text])))",
            "source",
            {"o'clock", "a, b", "x = (y)"},
        ),
    ],
)
def test_canonical_forms_are_recognized(
    definition: str, column: str, values: set[CheckValue]
) -> None:
    assert parse_check(definition, (column,)) == ActualCheck(definition, column, frozenset(values))


@pytest.mark.parametrize(
    ("definition", "columns"),
    [
        ("CHECK ((amount > (0)::numeric))", ("amount",)),
        ("CHECK ((low < high))", ("low", "high")),
        ("CHECK ((lower(code) = code))", ("code",)),
        ("CHECK ((source = ANY (ARRAY['a'::text])))", ("other",)),
        ("CHECK ((flag = ANY (ARRAY[true, false])))", ("flag",)),
        ("CHECK ((source = ANY (ARRAY['a'::text]))) NOT VALID", ("source",)),
        ("UNIQUE (source)", ("source",)),
    ],
)
def test_other_checks_are_unrecognized(definition: str, columns: tuple[str, ...]) -> None:
    assert parse_check(definition, columns) == ActualCheck(definition)


def test_unrecognized_check_is_shown_by_definition() -> None:
    assert str(ActualCheck("CHECK ((amount > 0))")) == "CHECK ((amount > 0))"
    assert str(ActualCheck("…", "source", frozenset({"manual", "collector"}))) == (
        "[collector, manual]"
    )
