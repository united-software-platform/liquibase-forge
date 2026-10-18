"""Фактические схемы для тестов Сверки."""

from __future__ import annotations

from forge.modeling.domain.column_type import parse_column_type
from forge.reconciliation.domain.actual_schema import ActualColumn, ActualSchema, ActualTable


def column(name: str, type_name: str, nullable: bool = True, **parameters: int) -> ActualColumn:
    column_type = parse_column_type(type_name, **parameters)
    return ActualColumn(name, column_type, str(column_type), nullable)


def customer(*extra: ActualColumn, key: tuple[str, ...] | None = ("id",)) -> ActualTable:
    """Таблица `customer`, совпадающая с `CUSTOMER` из моделей Миграции."""
    columns = (
        column("id", "uuid", nullable=False),
        column("email", "string", nullable=False, length=255),
        *extra,
    )
    return ActualTable("customer", columns, key)


def schema(*tables: ActualTable) -> ActualSchema:
    return ActualSchema(tables)
