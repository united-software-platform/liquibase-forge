"""Колонка и первичный ключ: объявленная допустимость NULL, непустой ключ без повторов."""

from __future__ import annotations

import dataclasses

import pytest

from forge.modeling.domain.column import Column
from forge.modeling.domain.column_type import parse_column_type
from forge.modeling.domain.identifier import ColumnName
from forge.modeling.domain.primary_key import PrimaryKey
from forge.modeling.domain.violation import ModelViolationError


def _names(*values: str) -> tuple[ColumnName, ...]:
    return tuple(ColumnName(value) for value in values)


@pytest.mark.parametrize("nullable", [True, False, None])
def test_column_keeps_declared_nullable(nullable: bool | None) -> None:
    column = Column(ColumnName("email"), parse_column_type("text"), nullable)

    assert column.nullable is nullable


def test_column_is_immutable() -> None:
    column = Column(ColumnName("id"), parse_column_type("uuid"))

    with pytest.raises(dataclasses.FrozenInstanceError):
        column.nullable = False  # type: ignore[misc]


def test_primary_key_keeps_order() -> None:
    key = PrimaryKey(_names("tenant_id", "id"))

    assert key.columns == _names("tenant_id", "id")
    assert ColumnName("id") in key
    assert ColumnName("code") not in key


def test_empty_primary_key() -> None:
    with pytest.raises(ModelViolationError) as caught:
        PrimaryKey(())

    assert [(v.path, v.code) for v in caught.value.violations] == [("", "empty_primary_key")]


def test_duplicate_primary_key_columns_are_reported_by_position() -> None:
    with pytest.raises(ModelViolationError) as caught:
        PrimaryKey(_names("id", "code", "id", "id"))

    assert [(v.path, v.code) for v in caught.value.violations] == [
        ("[2]", "primary_key_duplicate_column"),
        ("[3]", "primary_key_duplicate_column"),
    ]


def test_primary_key_is_immutable() -> None:
    key = PrimaryKey(_names("id"))

    with pytest.raises(dataclasses.FrozenInstanceError):
        key.columns = ()  # type: ignore[misc]
