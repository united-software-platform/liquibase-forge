"""Добавляющая разница между принятой моделью и моделью попытки."""

from __future__ import annotations

from forge.migration.domain.changes import (
    AddColumn,
    CreateTable,
    NonAdditiveChange,
    NonAdditiveChangeError,
    SchemaChange,
)
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.table import Table


class AdditiveDiff:
    """Доменный сервис: изменения схемы от принятой модели к модели попытки.

    Разрешены новая таблица и новая колонка существующей таблицы. Удаление таблицы
    или колонки, смена типа, итоговой допустимости NULL и первичного ключа — неаддитивные
    изменения; они собираются все и бросаются одним исключением. Переименование неотличимо
    от удаления и отклоняется как удаление.
    """

    def between(self, accepted: DataModel, attempt: DataModel) -> tuple[SchemaChange, ...]:
        rejected: list[NonAdditiveChange] = []
        for table in accepted.tables:
            if not attempt.has_table(table.name):
                rejected.append(
                    NonAdditiveChange(
                        "table_removed",
                        table.name.value,
                        None,
                        f"таблица {table.name} есть в принятой модели и удалена в модели попытки",
                    )
                )
                continue
            rejected += _table_changes(table, attempt.table(table.name))
        if rejected:
            raise NonAdditiveChangeError(rejected)

        changes: list[SchemaChange] = []
        for table in attempt.tables:
            if not accepted.has_table(table.name):
                changes.append(CreateTable(table))
                continue
            known = {column.name for column in accepted.table(table.name).columns}
            changes += [
                AddColumn(table.name, column, table.is_nullable(column.name))
                for column in table.columns
                if column.name not in known
            ]
        return tuple(changes)


def _table_changes(accepted: Table, attempt: Table) -> list[NonAdditiveChange]:
    table = accepted.name.value
    names = {column.name for column in attempt.columns}
    rejected: list[NonAdditiveChange] = []
    for column in accepted.columns:
        name = column.name.value
        if column.name not in names:
            rejected.append(
                NonAdditiveChange(
                    "column_removed",
                    table,
                    name,
                    f"колонка {table}.{name} есть в принятой модели и удалена в модели попытки",
                )
            )
            continue
        changed = attempt.column(column.name)
        if changed.type != column.type:
            rejected.append(
                NonAdditiveChange(
                    "column_type_changed",
                    table,
                    name,
                    f"тип колонки {table}.{name} изменён: {column.type} → {changed.type}",
                )
            )
        before, after = accepted.is_nullable(column.name), attempt.is_nullable(column.name)
        if before != after:
            rejected.append(
                NonAdditiveChange(
                    "column_nullable_changed",
                    table,
                    name,
                    f"допустимость NULL колонки {table}.{name} изменена: "
                    f"{_nullable(before)} → {_nullable(after)}",
                )
            )
    if accepted.primary_key != attempt.primary_key:
        rejected.append(
            NonAdditiveChange(
                "primary_key_changed",
                table,
                None,
                f"первичный ключ таблицы {table} изменён: {_key(accepted)} → {_key(attempt)}",
            )
        )
    return rejected


def _nullable(nullable: bool) -> str:
    return "NULL" if nullable else "NOT NULL"


def _key(table: Table) -> str:
    return "[" + ", ".join(column.value for column in table.primary_key.columns) + "]"
