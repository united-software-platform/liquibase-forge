"""Разница между принятой моделью и моделью попытки."""

from __future__ import annotations

from forge.migration.domain.changes import (
    AddColumn,
    CreateTable,
    DropColumn,
    DropTable,
    SchemaChange,
    UnsupportedChange,
    UnsupportedChangeError,
)
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.table import Table


class ModelDiff:
    """Доменный сервис: изменения схемы от принятой модели к модели попытки.

    Разрешены новая и удалённая таблица, новая и удалённая колонка существующей таблицы.
    Удаление колонки первичного ключа не даёт `DropColumn`: смена ключа уже отклоняется.
    Смена типа, итоговой допустимости NULL и первичного ключа — неподдерживаемые изменения;
    они собираются все и бросаются одним исключением. Переименование неотличимо от удаления
    и добавления и выражается ими.

    Порядок: удалённые таблицы в порядке принятой модели, удалённые колонки по таблицам
    и колонкам принятой модели, затем добавления в порядке модели попытки.
    """

    def between(self, accepted: DataModel, attempt: DataModel) -> tuple[SchemaChange, ...]:
        unsupported: list[UnsupportedChange] = []
        for table in accepted.tables:
            if attempt.has_table(table.name):
                unsupported += _table_changes(table, attempt.table(table.name))
        if unsupported:
            raise UnsupportedChangeError(unsupported)

        changes: list[SchemaChange] = [
            DropTable(table) for table in accepted.tables if not attempt.has_table(table.name)
        ]
        for table in accepted.tables:
            if attempt.has_table(table.name):
                changes += _dropped_columns(table, attempt.table(table.name))
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


def _dropped_columns(accepted: Table, attempt: Table) -> list[SchemaChange]:
    names = {column.name for column in attempt.columns}
    return [
        DropColumn(accepted.name, column, accepted.is_nullable(column.name))
        for column in accepted.columns
        if column.name not in names and column.name not in accepted.primary_key
    ]


def _table_changes(accepted: Table, attempt: Table) -> list[UnsupportedChange]:
    table = accepted.name.value
    names = {column.name for column in attempt.columns}
    rejected: list[UnsupportedChange] = []
    for column in accepted.columns:
        if column.name not in names:
            continue
        name = column.name.value
        changed = attempt.column(column.name)
        if changed.type != column.type:
            rejected.append(
                UnsupportedChange(
                    "column_type_changed",
                    table,
                    name,
                    f"тип колонки {table}.{name} изменён: {column.type} → {changed.type}",
                )
            )
        before, after = accepted.is_nullable(column.name), attempt.is_nullable(column.name)
        if before != after:
            rejected.append(
                UnsupportedChange(
                    "column_nullable_changed",
                    table,
                    name,
                    f"допустимость NULL колонки {table}.{name} изменена: "
                    f"{_nullable(before)} → {_nullable(after)}",
                )
            )
    if accepted.primary_key != attempt.primary_key:
        rejected.append(
            UnsupportedChange(
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
