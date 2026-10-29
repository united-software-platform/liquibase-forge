"""Seed и колонки с перечнем значений и генерацией значения."""

from __future__ import annotations

import pytest

from forge.modeling.domain.draft import ColumnDraft
from forge.seeding.domain.draft import SeedDraft
from forge.seeding.domain.factory import SeedFactory
from forge.seeding.domain.seed import SeedViolationError
from tests.seeding.support import NULL, i, model, row, s, seed, table

STATUS = model(
    table(
        "order_status",
        ColumnDraft("code", "string", length=16, check=("draft", "paid")),
        ColumnDraft("source", "text", check=("collector", "manual")),
        ColumnDraft("level", "integer", check=(1, 2)),
    ),
    table(
        "category",
        ColumnDraft("id", "bigint", generated="identity"),
        ColumnDraft("title", "text"),
        key=("id",),
    ),
)


def _violations(draft: SeedDraft) -> list[tuple[str, str]]:
    with pytest.raises(SeedViolationError) as error:
        SeedFactory().create(STATUS, draft)
    return [(v.path, v.code) for v in error.value.violations]


def test_values_from_list_are_valid() -> None:
    result = SeedFactory().create(
        STATUS,
        seed(("order_status", (row(code=s("draft"), level=i(1)), row(code=s("paid"))))),
    )

    assert len(result.tables[0].rows) == 2


def test_value_outside_list_is_violation() -> None:
    draft = seed(
        ("order_status", (row(code=s("draft")), row(code=s("paid")), row(code=s("cancelled"))))
    )

    assert _violations(draft) == [("tables[0].rows[2].code", "check_violated")]


def test_null_in_nullable_column_with_list() -> None:
    draft = seed(("order_status", (row(code=s("draft"), source=NULL, level=NULL),)))

    assert len(SeedFactory().create(STATUS, draft).tables[0].rows) == 1


def test_wrong_kind_is_not_checked_against_list() -> None:
    draft = seed(("order_status", (row(code=s("draft"), level=s("1")),)))

    assert _violations(draft) == [("tables[0].rows[0].level", "invalid_value")]


def test_integer_value_outside_list() -> None:
    draft = seed(("order_status", (row(code=s("draft"), level=i(3)),)))

    assert _violations(draft) == [("tables[0].rows[0].level", "check_violated")]


def test_generated_key_requires_explicit_value() -> None:
    assert _violations(seed(("category", (row(title=s("Книги")),)))) == [
        ("tables[0].rows[0].id", "null_value")
    ]


def test_generated_key_with_explicit_value() -> None:
    result = SeedFactory().create(STATUS, seed(("category", (row(id=i(1), title=s("Книги")),))))

    assert len(result.tables[0].rows) == 1
