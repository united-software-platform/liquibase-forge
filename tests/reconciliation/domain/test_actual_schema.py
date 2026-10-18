"""Фактическая схема: доступ по имени, запись типа, неизменяемость."""

from __future__ import annotations

import dataclasses

import pytest

from forge.reconciliation.domain.actual_schema import ActualColumn
from tests.reconciliation.schemas import customer, schema


def test_lookup_by_name() -> None:
    actual = schema(customer())

    table = actual.table("customer")
    assert table is not None
    assert table.column("email") is not None
    assert table.column("phone") is None
    assert actual.table("invoice") is None


def test_type_text() -> None:
    table = customer()
    email = table.column("email")
    assert email is not None
    assert email.type_text == "string(255)"
    assert ActualColumn("level", None, "smallint", True).type_text == "smallint"


def test_schema_is_immutable() -> None:
    actual = schema(customer())

    with pytest.raises(dataclasses.FrozenInstanceError):
        actual.tables = ()  # type: ignore[misc]
