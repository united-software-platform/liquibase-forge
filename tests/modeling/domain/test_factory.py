"""Фабрика модели: сборка из черновика и все нарушения сразу с путями от корня файла."""

from __future__ import annotations

import pytest

from forge.modeling.domain.column_type import TypeKind
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.draft import ColumnDraft, DataModelDraft, TableDraft
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.domain.identifier import ColumnName, TableName
from forge.modeling.domain.violation import ModelViolationError
from tests.modeling.example import EXAMPLE


def _table(
    position: int, name: str, *columns: ColumnDraft, key: tuple[str, ...] = ("id",)
) -> TableDraft:
    return TableDraft(position, name, columns or (ColumnDraft("id", "bigint"),), key)


def _violations(*tables: TableDraft) -> list[tuple[str, str]]:
    with pytest.raises(ModelViolationError) as caught:
        DataModelFactory().create(DataModelDraft(tables))
    return [(v.path, v.code) for v in caught.value.violations]


def test_example_model_is_built() -> None:
    model = DataModelFactory().create(EXAMPLE)

    assert isinstance(model, DataModel)
    invoice_line = model.table(TableName("invoice_line"))
    assert [column.name.value for column in invoice_line.columns][:2] == ["invoice_id", "line_no"]
    assert invoice_line.primary_key.columns == (ColumnName("invoice_id"), ColumnName("line_no"))
    assert invoice_line.column(ColumnName("amount")).type.precision == 12
    assert invoice_line.is_nullable(ColumnName("line_no")) is False
    assert invoice_line.is_nullable(ColumnName("is_paid")) is True
    kinds = {column.type.kind for table in model.tables for column in table.columns}
    assert kinds == set(TypeKind)


def test_empty_draft_gives_empty_model() -> None:
    assert DataModelFactory().create(DataModelDraft(())).tables == ()


def test_violations_in_two_tables_are_reported_together() -> None:
    assert _violations(
        _table(0, "customer", ColumnDraft("id", "bigint"), ColumnDraft("email", "string")),
        _table(1, "invoice", ColumnDraft("id", "bigint"), key=("id", "code")),
    ) == [
        ("tables[0].columns[1].length", "missing_type_parameter"),
        ("tables[1].primary_key[1]", "primary_key_unknown_column"),
    ]


def test_column_name_and_type_violations_are_reported_together() -> None:
    assert _violations(
        _table(0, "customer", ColumnDraft("id", "bigint"), ColumnDraft("Email", "varchar"))
    ) == [
        ("tables[0].columns[1].name", "invalid_identifier"),
        ("tables[0].columns[1].type", "unknown_type"),
    ]


def test_table_invariants_are_checked_despite_invalid_table_name() -> None:
    assert _violations(
        _table(0, "order", ColumnDraft("id", "bigint"), ColumnDraft("id", "text"))
    ) == [
        ("tables[0].name", "reserved_identifier"),
        ("tables[0].columns[1].name", "duplicate_name"),
    ]


def test_table_invariants_wait_for_valid_columns() -> None:
    assert _violations(
        _table(0, "customer", ColumnDraft("id", "bigint"), ColumnDraft("xmin", "bigint")),
    ) == [("tables[0].columns[1].name", "reserved_identifier")]


def test_primary_key_with_invalid_name_is_unknown_column() -> None:
    assert _violations(_table(0, "customer", key=("id", "Code"))) == [
        ("tables[0].primary_key[1]", "primary_key_unknown_column")
    ]


def test_primary_key_violations_are_prefixed() -> None:
    assert _violations(_table(0, "customer", key=())) == [
        ("tables[0].primary_key", "empty_primary_key")
    ]
    assert _violations(_table(0, "customer", key=("id", "id"))) == [
        ("tables[0].primary_key[1]", "primary_key_duplicate_column")
    ]


def test_primary_key_nullable_path_is_from_root() -> None:
    assert _violations(_table(3, "customer", ColumnDraft("id", "bigint", nullable=True))) == [
        ("tables[3].columns[0].nullable", "primary_key_nullable")
    ]


def test_duplicate_table_name_comes_first_among_its_table_violations() -> None:
    assert _violations(
        _table(0, "customer"),
        _table(1, "customer", ColumnDraft("id", "string")),
        _table(2, "invoice", key=()),
    ) == [
        ("tables[1].name", "duplicate_name"),
        ("tables[1].columns[0].length", "missing_type_parameter"),
        ("tables[2].primary_key", "empty_primary_key"),
    ]


def test_duplicate_name_is_found_among_invalid_tables() -> None:
    assert _violations(
        _table(0, "customer", key=("code",)),
        _table(1, "customer", key=("code",)),
    ) == [
        ("tables[0].primary_key[0]", "primary_key_unknown_column"),
        ("tables[1].name", "duplicate_name"),
        ("tables[1].primary_key[0]", "primary_key_unknown_column"),
    ]


def test_positions_come_from_draft() -> None:
    # Таблица на позиции 0 исключена из черновика из-за структурных нарушений
    assert _violations(_table(1, "customer", key=("code",))) == [
        ("tables[1].primary_key[0]", "primary_key_unknown_column")
    ]


def test_violation_order_is_stable() -> None:
    draft = (
        _table(0, "Customer", ColumnDraft("id", "decimal")),
        _table(1, "invoice", ColumnDraft("id", "integer", length=3), key=("id", "id")),
    )

    assert _violations(*draft) == _violations(*draft)
