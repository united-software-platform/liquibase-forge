"""Имена таблиц и колонок: шаблон, длина, зарезервированные имена."""

from __future__ import annotations

import pytest

from forge.modeling.domain.identifier import ColumnName, Identifier, TableName
from forge.modeling.domain.violation import ModelViolationError


def _code(factory: type[Identifier], value: str) -> str:
    with pytest.raises(ModelViolationError) as caught:
        factory(value)
    (violation,) = caught.value.violations
    assert violation.path == ""
    return violation.code


@pytest.mark.parametrize("value", ["customer", "a", "order_line_2", "a" * 63])
def test_valid_column_name(value: str) -> None:
    assert ColumnName(value).value == value


@pytest.mark.parametrize("value", ["Customer", "2nd", "_id", "e-mail", "", "имя", "a" * 64])
@pytest.mark.parametrize("factory", [TableName, ColumnName])
def test_invalid_identifier(factory: type[Identifier], value: str) -> None:
    assert _code(factory, value) == "invalid_identifier"


def test_table_name_is_limited_to_60_characters() -> None:
    assert TableName("t" * 60).value == "t" * 60
    assert _code(TableName, "t" * 61) == "invalid_identifier"


def test_column_name_allows_63_characters() -> None:
    assert ColumnName("c" * 63).value == "c" * 63


@pytest.mark.parametrize("value", ["order", "user", "table", "select", "left"])
@pytest.mark.parametrize("factory", [TableName, ColumnName])
def test_keyword_is_reserved(factory: type[Identifier], value: str) -> None:
    assert _code(factory, value) == "reserved_identifier"


@pytest.mark.parametrize("value", ["xmin", "ctid", "tableoid"])
def test_system_column_is_reserved_for_column(value: str) -> None:
    assert _code(ColumnName, value) == "reserved_identifier"
    assert TableName(value).value == value


@pytest.mark.parametrize("value", ["databasechangelog", "databasechangeloglock"])
def test_liquibase_table_is_reserved_for_table(value: str) -> None:
    assert _code(TableName, value) == "reserved_identifier"
    assert ColumnName(value).value == value


def test_identifier_is_value_object() -> None:
    assert ColumnName("id") == ColumnName("id")
    assert str(TableName("customer")) == "customer"
