"""Фабрика seed: таблицы, строки, NOT NULL, первичный ключ и наборы `unique`."""

from __future__ import annotations

import pytest

from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.draft import ColumnDraft
from forge.modeling.domain.identifier import ColumnName, TableName
from forge.seeding.domain.draft import SeedDraft
from forge.seeding.domain.factory import SeedFactory
from forge.seeding.domain.seed import Seed, SeedViolationError
from forge.seeding.domain.seed_value import SeedValue
from tests.seeding.support import CODE, NULL, ORDER_STATUS, i, model, row, s, seed, table

MODEL = model(
    ORDER_STATUS,
    table("customer", ColumnDraft("id", "bigint"), key=("id",)),
)


def _violations(draft: SeedDraft, data_model: DataModel = MODEL) -> list[tuple[str, str]]:
    with pytest.raises(SeedViolationError) as error:
        SeedFactory().create(data_model, draft)
    return [(v.path, v.code) for v in error.value.violations]


def _seed(draft: SeedDraft, data_model: DataModel = MODEL) -> Seed:
    return SeedFactory().create(data_model, draft)


def test_empty_seed() -> None:
    assert _seed(seed()).tables == ()


def test_table_without_rows_belongs_to_seed() -> None:
    result = _seed(seed(("order_status", ())))

    assert [t.name for t in result.tables] == [TableName("order_status")]
    assert result.tables[0].rows == ()
    assert not result.has_table(TableName("customer"))


def test_unknown_table_rows_are_not_checked() -> None:
    draft = seed(("order_state", (row(label=s("x")),)))

    assert _violations(draft) == [("tables[0].name", "unknown_table")]


def test_duplicate_table() -> None:
    draft = seed(("order_status", ()), ("customer", ()), ("order_status", ()))

    assert _violations(draft) == [("tables[2].name", "duplicate_table")]


def test_unknown_column() -> None:
    draft = seed(
        (
            "order_status",
            (
                row(code=s("new"), title=s("Новый")),
                row(code=s("draft"), title=s("Ч"), label=s("x")),
            ),
        )
    )

    assert _violations(draft) == [("tables[0].rows[1].label", "unknown_column")]


def test_missing_nullable_column_is_null() -> None:
    result = _seed(seed(("order_status", (row(code=s("new"), title=s("Новый")),))))

    seed_row = result.tables[0].rows[0]
    assert seed_row.value(ColumnName("description")).is_null()
    assert seed_row.value(ColumnName("code")) == SeedValue("new")
    assert [name.value for name, _ in seed_row.values] == [
        "code",
        "title",
        "description",
        "external_code",
    ]


def test_missing_primary_key_value() -> None:
    draft = seed(("order_status", (row(title=s("Новый")),)))

    assert _violations(draft) == [("tables[0].rows[0].code", "null_value")]


def test_explicit_null_in_not_null_column() -> None:
    rows = (
        row(code=s("a"), title=s("A")),
        row(code=s("b"), title=s("B")),
        row(code=s("c"), title=NULL),
    )

    assert _violations(seed(("order_status", rows))) == [("tables[0].rows[2].title", "null_value")]


def test_row_violations_in_order_of_row_then_model() -> None:
    draft = seed(("order_status", (row(description=i(1), label=s("x")),)))

    assert _violations(draft) == [
        ("tables[0].rows[0].description", "invalid_value"),
        ("tables[0].rows[0].label", "unknown_column"),
        ("tables[0].rows[0].code", "null_value"),
        ("tables[0].rows[0].title", "null_value"),
    ]


def test_duplicate_primary_key_on_repeated_row() -> None:
    rows = (
        row(code=s("draft"), title=s("Черновик")),
        row(code=s("new"), title=s("Новый")),
        row(code=s("paid"), title=s("Оплачен")),
        row(code=s("draft"), title=s("Ещё черновик")),
    )

    assert _violations(seed(("order_status", rows))) == [
        ("tables[0].rows[3]", "duplicate_primary_key")
    ]


def test_primary_key_compared_by_normalized_form() -> None:
    fee = model(
        table("fee", ColumnDraft("amount", "decimal", precision=5, scale=2), key=("amount",))
    )
    draft = seed(("fee", (row(amount=s("1.50")), row(amount=s("1.5")))))

    assert _violations(draft, fee) == [("tables[0].rows[1]", "duplicate_primary_key")]


def test_duplicate_unique_set() -> None:
    rows = (
        row(code=s("new"), title=s("Новый")),
        row(code=s("draft"), title=s("Черновик")),
        row(code=s("draft2"), title=s("Черновик")),
    )

    assert _violations(seed(("order_status", rows))) == [("tables[0].rows[2]", "duplicate_unique")]


def test_null_in_unique_set_is_not_compared() -> None:
    rows = (row(code=s("a"), title=s("A")), row(code=s("b"), title=s("B")))

    assert len(_seed(seed(("order_status", rows))).tables[0].rows) == 2


def test_row_with_broken_value_does_not_take_part_in_keys() -> None:
    rows = (
        row(code=s("draft"), title=s("Черновик"), description=i(1)),
        row(code=s("draft"), title=s("Черновик")),
    )

    assert _violations(seed(("order_status", rows))) == [
        ("tables[0].rows[0].description", "invalid_value")
    ]


def test_primary_key_repeats_come_before_unique_repeats() -> None:
    rows = (
        row(code=s("a"), title=s("T")),
        row(code=s("b"), title=s("T")),
        row(code=s("a"), title=s("U")),
    )

    assert _violations(seed(("order_status", rows))) == [
        ("tables[0].rows[2]", "duplicate_primary_key"),
        ("tables[0].rows[1]", "duplicate_unique"),
    ]


def test_excluded_table_keeps_positions() -> None:
    draft = SeedDraft(seed(("order_status", ()), ("order_state", ())).tables[1:], ("order_status",))

    assert _violations(draft) == [("tables[1].name", "unknown_table")]


def test_column_lookup_uses_model_columns() -> None:
    codes = model(table("kind", CODE))

    result = _seed(seed(("kind", (row(code=s("x")),))), codes)

    assert result.tables[0].rows[0].key([ColumnName("code")]) == (SeedValue("x"),)
