"""Генерация значения и перечень значений колонки: правила колонки, таблицы и фабрики."""

from __future__ import annotations

import pytest

from forge.modeling.domain.column import Column
from forge.modeling.domain.column_type import parse_column_type
from forge.modeling.domain.draft import ColumnDraft, DataModelDraft, TableDraft
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.domain.generation import Generation, parse_generation
from forge.modeling.domain.identifier import ColumnName
from forge.modeling.domain.value_list import ListValue, ValueList
from forge.modeling.domain.violation import ModelViolationError


def _violations(*columns: ColumnDraft, key: tuple[str, ...] = ("id",)) -> list[tuple[str, str]]:
    table = TableDraft(0, "event", (ColumnDraft("id", "bigint"), *columns), key)
    with pytest.raises(ModelViolationError) as caught:
        DataModelFactory().create(DataModelDraft((table,)))
    return [(v.path, v.code) for v in caught.value.violations]


def _model(*columns: ColumnDraft, key: tuple[str, ...] = ("id",)) -> Column:
    table = TableDraft(0, "event", columns, key)
    model = DataModelFactory().create(DataModelDraft((table,)))
    return model.tables[0].columns[-1]


def test_identity_is_the_only_generation() -> None:
    assert parse_generation("identity") is Generation.IDENTITY


def test_unknown_generation() -> None:
    with pytest.raises(ModelViolationError) as caught:
        parse_generation("sequence")

    assert [(v.path, v.code) for v in caught.value.violations] == [
        ("generated", "unknown_generation")
    ]


def test_primary_key_with_generation() -> None:
    column = _model(ColumnDraft("id", "bigint", generated="identity"))

    assert column.generated is Generation.IDENTITY


def test_generation_outside_key_is_not_null_without_nullable() -> None:
    table = TableDraft(
        0,
        "event",
        (ColumnDraft("id", "uuid"), ColumnDraft("seq_no", "integer", generated="identity")),
        ("id",),
    )

    model = DataModelFactory().create(DataModelDraft((table,)))

    assert model.tables[0].is_nullable(ColumnName("seq_no")) is False


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        (
            ColumnDraft("ref", "uuid", generated="identity"),
            [("tables[0].columns[1].generated", "generated_requires_integer")],
        ),
        (
            ColumnDraft("seq_no", "bigint", nullable=True, generated="identity"),
            [("tables[0].columns[1].nullable", "generated_nullable")],
        ),
        (
            ColumnDraft("seq_no", "bigint", generated="sequence"),
            [("tables[0].columns[1].generated", "unknown_generation")],
        ),
    ],
)
def test_generation_rules(column: ColumnDraft, expected: list[tuple[str, str]]) -> None:
    assert _violations(column) == expected


def test_second_generated_column_is_duplicate() -> None:
    violations = _violations(
        ColumnDraft("seq_no", "integer", generated="identity"),
        ColumnDraft("note", "text"),
        ColumnDraft("other_no", "bigint", generated="identity"),
        key=("seq_no",),
    )

    assert violations == [("tables[0].columns[3].generated", "duplicate_generated")]


def test_column_with_value_list() -> None:
    column = _model(
        ColumnDraft("id", "bigint"),
        ColumnDraft("source", "string", length=16, check=("collector", "manual")),
    )

    assert column.check == ValueList(("manual", "collector"))


def test_value_list_is_compared_without_order() -> None:
    assert ValueList(("a", "b")) == ValueList(("b", "a"))
    assert hash(ValueList(("a", "b"))) == hash(ValueList(("b", "a")))
    assert ValueList((1,)) != ValueList(("1",))
    assert ValueList((1,)) != ValueList((True,))


def test_value_list_sorted_values() -> None:
    assert ValueList(("manual", "collector")).sorted_values() == ("collector", "manual")
    assert ValueList((3, 1, 2)).sorted_values() == (1, 2, 3)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((), [("tables[0].columns[1].check", "check_empty")]),
        (
            ("manual", "collector", "manual"),
            [("tables[0].columns[1].check[2]", "check_duplicate_value")],
        ),
    ],
)
def test_value_list_rules(values: tuple[ListValue, ...], expected: list[tuple[str, str]]) -> None:
    assert _violations(ColumnDraft("source", "text", check=values)) == expected


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        (
            ColumnDraft("flag", "boolean", check=(True,)),
            [("tables[0].columns[1].check", "check_unsupported_type")],
        ),
        (
            ColumnDraft("source", "text", check=("manual", 404)),
            [("tables[0].columns[1].check[1]", "check_value_wrong_kind")],
        ),
        (
            ColumnDraft("source", "string", length=6, check=("manual", "collector")),
            [("tables[0].columns[1].check[1]", "check_value_out_of_range")],
        ),
        (
            ColumnDraft("level", "integer", check=(1, "2")),
            [("tables[0].columns[1].check[1]", "check_value_wrong_kind")],
        ),
        (
            ColumnDraft("level", "integer", check=(1, True)),
            [("tables[0].columns[1].check[1]", "check_value_wrong_kind")],
        ),
        (
            ColumnDraft("level", "integer", check=(1, None, 1.5)),
            [
                ("tables[0].columns[1].check[1]", "check_value_wrong_kind"),
                ("tables[0].columns[1].check[2]", "check_value_wrong_kind"),
            ],
        ),
        (
            ColumnDraft("level", "integer", check=(1, 3_000_000_000)),
            [("tables[0].columns[1].check[1]", "check_value_out_of_range")],
        ),
        (
            ColumnDraft("level", "bigint", check=(3_000_000_000, 2**63)),
            [("tables[0].columns[1].check[1]", "check_value_out_of_range")],
        ),
        (
            ColumnDraft("seq_no", "integer", generated="identity", check=(1, 2)),
            [("tables[0].columns[1].check", "check_with_generated")],
        ),
    ],
)
def test_value_list_kind_rules(column: ColumnDraft, expected: list[tuple[str, str]]) -> None:
    assert _violations(column) == expected


def test_value_list_column_allows_null() -> None:
    table = TableDraft(
        0,
        "event",
        (ColumnDraft("id", "bigint"), ColumnDraft("source", "text", check=("a", "b"))),
        ("id",),
    )

    model = DataModelFactory().create(DataModelDraft((table,)))

    assert model.tables[0].is_nullable(ColumnName("source")) is True


def test_column_rejects_incompatible_value_list_directly() -> None:
    with pytest.raises(ModelViolationError) as caught:
        Column(ColumnName("flag"), parse_column_type("uuid"), check=ValueList(("a",)))

    assert [(v.path, v.code) for v in caught.value.violations] == [
        ("check", "check_unsupported_type")
    ]
