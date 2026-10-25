"""Перевод значений `psycopg` в нормализованную форму seed и чтение строк таблиц."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest

from forge.modeling.domain.column_type import ColumnType, TypeKind
from forge.modeling.domain.draft import ColumnDraft
from forge.modeling.domain.identifier import ColumnName, TableName
from forge.seeding.domain.seed_value import SeedValue, SeedValueFactory
from forge.seeding.infrastructure.postgres_rows import PsycopgTableRowsReader, raw_value
from forge.shared.application.settings import DatabaseUnavailableError
from forge.shared.domain.target_database import TargetDatabase
from forge.shared.infrastructure.postgres import PostgresConnector
from tests.seeding.support import CODE, ORDER_STATUS, model, table

DATABASE = TargetDatabase("lbfr-db-test", 5432, "forge")
MSK = timezone(timedelta(hours=3))


def _normalized(column_type: ColumnType, value: object) -> SeedValue:
    result = SeedValueFactory().create(column_type, raw_value(value))
    assert isinstance(result, SeedValue), result
    return result


@pytest.mark.parametrize(
    ("column_type", "value", "expected"),
    [
        (ColumnType(TypeKind.INTEGER), 42, 42),
        (ColumnType(TypeKind.BIGINT), -(2**40), -(2**40)),
        (ColumnType(TypeKind.BOOLEAN), True, True),
        (ColumnType(TypeKind.BOOLEAN), False, False),
        (ColumnType(TypeKind.STRING, length=32), "draft", "draft"),
        (ColumnType(TypeKind.TEXT), "Черновик", "Черновик"),
        (ColumnType(TypeKind.DECIMAL, precision=10, scale=2), Decimal("1.50"), "1.5"),
        (ColumnType(TypeKind.DECIMAL, precision=10, scale=2), Decimal("-0.00"), "0"),
        (ColumnType(TypeKind.DECIMAL, precision=10, scale=2), Decimal("12.00"), "12"),
        (ColumnType(TypeKind.DATE), date(2026, 1, 1), "2026-01-01"),
        (ColumnType(TypeKind.TIMESTAMP), datetime(2026, 1, 1, 9, 30), "2026-01-01T09:30:00"),
        (
            ColumnType(TypeKind.TIMESTAMP),
            datetime(2026, 1, 1, 9, 30, 0, 500000),
            "2026-01-01T09:30:00.5",
        ),
        (
            ColumnType(TypeKind.TIMESTAMP_TZ),
            datetime(2026, 1, 1, 3, 0, tzinfo=MSK),
            "2026-01-01T00:00:00Z",
        ),
        (
            ColumnType(TypeKind.TIMESTAMP_TZ),
            datetime(2026, 1, 1, 0, 0, 0, 120000, tzinfo=UTC),
            "2026-01-01T00:00:00.12Z",
        ),
        (
            ColumnType(TypeKind.UUID),
            UUID("0b6d2f7e-3c1a-4c55-9e0f-6a7d8b9c0d1e"),
            "0b6d2f7e-3c1a-4c55-9e0f-6a7d8b9c0d1e",
        ),
        (ColumnType(TypeKind.TEXT), None, None),
    ],
)
def test_value_from_database_takes_seed_form(
    column_type: ColumnType, value: object, expected: int | bool | str | None
) -> None:
    assert _normalized(column_type, value) == SeedValue(expected)


def test_database_and_seed_notations_are_one_value() -> None:
    decimal = ColumnType(TypeKind.DECIMAL, precision=10, scale=2)
    seed_form = SeedValueFactory().create(decimal, raw_value("1.50"))

    assert _normalized(decimal, Decimal("1.5")) == seed_form


class _Connection:
    def __init__(self, rows: dict[str, list[tuple[object, ...]]]) -> None:
        self._rows = rows
        self.queries: list[str] = []

    def execute(self, query: Any) -> _Connection:
        text = query.as_string(None)
        self.queries.append(text)
        self._last = next(rows for name, rows in self._rows.items() if f'"{name}"' in text)
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._last


class _Connector:
    def __init__(self, rows: dict[str, list[tuple[object, ...]]]) -> None:
        self.connection = _Connection(rows)

    @contextmanager
    def connect(self, database: TargetDatabase) -> Iterator[_Connection]:
        yield self.connection


def _reader(connector: _Connector) -> PsycopgTableRowsReader:
    return PsycopgTableRowsReader(cast(PostgresConnector, connector))


def test_reads_only_given_tables_in_key_order() -> None:
    data_model = model(ORDER_STATUS, table("customer", CODE))
    connector = _Connector(
        {
            "order_status": [("draft", "Черновик", None, None)],
            "customer": [("c1",)],
        }
    )

    rows = _reader(connector).rows(DATABASE, (data_model.table(TableName("order_status")),))

    assert connector.connection.queries == [
        'SELECT "code", "title", "description", "external_code" '
        'FROM "public"."order_status" ORDER BY "code"'
    ]
    (draft,) = rows[TableName("order_status")]
    assert draft.value(ColumnName("title")) == SeedValue("Черновик")
    assert draft.value(ColumnName("description")).is_null()


def test_value_outside_model_type_is_environment_error() -> None:
    data_model = model(table("rate", CODE, ColumnDraft("value", "integer", nullable=False)))
    connector = _Connector({"rate": [("a", "не число")]})

    with pytest.raises(DatabaseUnavailableError, match=r"rate\.value не приводится"):
        _reader(connector).rows(DATABASE, data_model.tables)
