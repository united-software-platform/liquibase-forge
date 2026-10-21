"""Таблица: колонки, уникальность имён, ссылки ключа, NOT NULL колонок ключа."""

from __future__ import annotations

import pytest

from forge.modeling.domain.column import Column
from forge.modeling.domain.column_type import parse_column_type
from forge.modeling.domain.identifier import ColumnName, TableName
from forge.modeling.domain.primary_key import PrimaryKey
from forge.modeling.domain.table import Table
from forge.modeling.domain.violation import ModelViolationError


def _column(name: str, nullable: bool | None = None, type_name: str = "integer") -> Column:
    return Column(ColumnName(name), parse_column_type(type_name), nullable)


def _key(*names: str) -> PrimaryKey:
    return PrimaryKey(tuple(ColumnName(name) for name in names))


def _violations(columns: tuple[Column, ...], key: PrimaryKey) -> list[tuple[str, str]]:
    with pytest.raises(ModelViolationError) as caught:
        Table(TableName("customer"), columns, key)
    return [(v.path, v.code) for v in caught.value.violations]


def test_valid_table() -> None:
    table = Table(
        TableName("customer"), (_column("id"), _column("email", type_name="text")), _key("id")
    )

    assert [column.name.value for column in table.columns] == ["id", "email"]
    assert table.column(ColumnName("email")).type == parse_column_type("text")


def test_primary_key_column_without_nullable_is_not_null() -> None:
    table = Table(TableName("customer"), (_column("id"), _column("email")), _key("id"))

    assert table.is_nullable(ColumnName("id")) is False
    assert table.is_nullable(ColumnName("email")) is True


def test_explicit_nullable_false_is_kept() -> None:
    table = Table(TableName("customer"), (_column("id", False), _column("code", False)), _key("id"))

    assert table.is_nullable(ColumnName("id")) is False
    assert table.is_nullable(ColumnName("code")) is False


def test_empty_columns() -> None:
    assert _violations((), _key("id")) == [
        ("columns", "empty_columns"),
        ("primary_key[0]", "primary_key_unknown_column"),
    ]


def test_duplicate_column_reports_every_repeat() -> None:
    assert _violations(
        (_column("id"), _column("code"), _column("id"), _column("id")), _key("id")
    ) == [
        ("columns[2].name", "duplicate_name"),
        ("columns[3].name", "duplicate_name"),
    ]


def test_primary_key_references_unknown_column() -> None:
    assert _violations((_column("id"),), _key("id", "code")) == [
        ("primary_key[1]", "primary_key_unknown_column")
    ]


def test_primary_key_column_declared_nullable() -> None:
    assert _violations((_column("id", True), _column("code", True)), _key("id")) == [
        ("columns[0].nullable", "primary_key_nullable")
    ]


def test_all_table_violations_are_reported_together() -> None:
    columns = (_column("id", True), _column("id"))

    assert _violations(columns, _key("id", "code")) == [
        ("columns[1].name", "duplicate_name"),
        ("primary_key[1]", "primary_key_unknown_column"),
        ("columns[0].nullable", "primary_key_nullable"),
    ]


def test_table_identity_is_its_name() -> None:
    first = Table(TableName("customer"), (_column("id"),), _key("id"))
    second = Table(TableName("customer"), (_column("code"),), _key("code"))

    assert first == second
    assert len({first, second}) == 1


def test_unknown_column_lookup_is_error() -> None:
    table = Table(TableName("customer"), (_column("id"),), _key("id"))

    with pytest.raises(KeyError):
        table.column(ColumnName("code"))
