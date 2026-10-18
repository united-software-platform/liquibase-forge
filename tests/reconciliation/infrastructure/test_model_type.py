"""Обратное отображение типов PostgreSQL в типы модели."""

from __future__ import annotations

import pytest

from forge.modeling.domain.column_type import parse_column_type
from forge.reconciliation.infrastructure.postgres_introspection import model_type


@pytest.mark.parametrize(
    ("database_type", "name", "parameters"),
    [
        ("integer", "integer", {}),
        ("bigint", "bigint", {}),
        ("boolean", "boolean", {}),
        ("character varying(255)", "string", {"length": 255}),
        ("text", "text", {}),
        ("numeric(12,2)", "decimal", {"precision": 12, "scale": 2}),
        ("date", "date", {}),
        ("timestamp without time zone", "timestamp", {}),
        ("timestamp with time zone", "timestamp_tz", {}),
        ("uuid", "uuid", {}),
    ],
)
def test_types_of_format(database_type: str, name: str, parameters: dict[str, int]) -> None:
    assert model_type(database_type) == parse_column_type(name, **parameters)


@pytest.mark.parametrize(
    "database_type", ["smallint", "character varying", "numeric", "character(3)", "jsonb"]
)
def test_types_outside_format(database_type: str) -> None:
    assert model_type(database_type) is None
