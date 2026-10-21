"""Модель данных: уникальность имён таблиц, пустая модель, доступ к таблицам."""

from __future__ import annotations

import pytest

from forge.modeling.domain.column import Column
from forge.modeling.domain.column_type import parse_column_type
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.identifier import ColumnName, TableName
from forge.modeling.domain.primary_key import PrimaryKey
from forge.modeling.domain.table import Table
from forge.modeling.domain.violation import ModelViolationError


def _table(name: str) -> Table:
    return Table(
        TableName(name),
        (Column(ColumnName("id"), parse_column_type("bigint")),),
        PrimaryKey((ColumnName("id"),)),
    )


def test_empty_model_is_valid() -> None:
    assert DataModel(()).tables == ()


def test_tables_keep_order_and_are_found_by_name() -> None:
    model = DataModel((_table("customer"), _table("invoice")))

    assert [table.name.value for table in model.tables] == ["customer", "invoice"]
    assert model.table(TableName("invoice")) is model.tables[1]
    assert model.has_table(TableName("customer"))
    assert not model.has_table(TableName("payment"))


def test_duplicate_table_name_reports_each_repeat() -> None:
    with pytest.raises(ModelViolationError) as caught:
        DataModel((_table("customer"), _table("invoice"), _table("customer")))

    assert [(v.path, v.code) for v in caught.value.violations] == [
        ("tables[2].name", "duplicate_name")
    ]


def test_unknown_table_lookup_is_error() -> None:
    with pytest.raises(KeyError):
        DataModel(()).table(TableName("customer"))
