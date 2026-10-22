"""Запись changelog в формате YAML Liquibase и обратное чтение его сводки.

Отображение типов модели в типы Liquibase для PostgreSQL живёт здесь: это знание о Liquibase
и СУБД, а не о формате модели. Порядок ключей задаёт код, поэтому повторная запись того же
changelog даёт побайтово тот же файл.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from forge.migration.application.changelog_storage import (
    ChangelogSummary,
    ChangelogUnreadableError,
)
from forge.migration.domain.changelog import Changelog, ChangeSet
from forge.migration.domain.changes import (
    AddColumn,
    CreateTable,
    DropColumn,
    DropTable,
    SchemaChange,
)
from forge.modeling.domain.column import Column
from forge.modeling.domain.column_type import ColumnType, TypeKind
from forge.modeling.domain.identifier import TableName
from forge.modeling.domain.table import Table

AUTHOR = "forge"

_TYPES: dict[TypeKind, str] = {
    TypeKind.INTEGER: "INTEGER",
    TypeKind.BIGINT: "BIGINT",
    TypeKind.BOOLEAN: "BOOLEAN",
    TypeKind.TEXT: "TEXT",
    TypeKind.DATE: "DATE",
    TypeKind.TIMESTAMP: "TIMESTAMP WITHOUT TIME ZONE",
    TypeKind.TIMESTAMP_TZ: "TIMESTAMP WITH TIME ZONE",
    TypeKind.UUID: "UUID",
}


def liquibase_type(column_type: ColumnType) -> str:
    """Тип Liquibase для PostgreSQL по типу колонки модели."""
    if column_type.kind is TypeKind.STRING:
        return f"VARCHAR({column_type.length})"
    if column_type.kind is TypeKind.DECIMAL:
        return f"NUMERIC({column_type.precision}, {column_type.scale})"
    return _TYPES[column_type.kind]


def primary_key_name(table: str) -> str:
    """Имя ограничения первичного ключа таблицы."""
    return f"pk_{table}"


def render_changelog(changelog: Changelog) -> str:
    """Текст changelog: заголовочный комментарий и YAML Liquibase."""
    document = {"databaseChangeLog": [_changeset(changelog, item) for item in changelog.changesets]}
    body = yaml.safe_dump(
        document, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000
    )
    header = (
        f"# Changelog операции {changelog.stamp}: построен forge generate, вручную не правится\n"
    )
    return header + body


def _changeset(changelog: Changelog, item: ChangeSet) -> dict[str, Any]:
    changeset: dict[str, Any] = {
        "id": item.id,
        "author": AUTHOR,
        "logicalFilePath": changelog.logical_file_path,
        "changes": _forward(item.change),
    }
    # Откат создания Liquibase выводит сам; откат удаления задаётся явно по принятой модели
    if isinstance(item.change, DropTable | DropColumn):
        changeset["rollback"] = _restore(item.change)
    return {"changeSet": changeset}


def _forward(change: SchemaChange) -> list[dict[str, Any]]:
    if isinstance(change, CreateTable):
        return _create_table(change.table)
    if isinstance(change, AddColumn):
        return _add_column(change.table, change.column, change.nullable)
    if isinstance(change, DropTable):
        return [{"dropTable": {"tableName": change.table.name.value}}]
    return [
        {
            "dropColumn": {
                "tableName": change.table.value,
                "columnName": change.column.name.value,
            }
        }
    ]


def _restore(change: DropTable | DropColumn) -> list[dict[str, Any]]:
    """Откат удаления: структура объекта по принятой модели, данные не восстанавливаются."""
    if isinstance(change, DropTable):
        return _create_table(change.table)
    return _add_column(change.table, change.column, change.nullable)


def _create_table(table: Table) -> list[dict[str, Any]]:
    name = table.name.value
    columns = [_column(column, table.is_nullable(column.name)) for column in table.columns]
    return [
        {"createTable": {"tableName": name, "columns": columns}},
        {
            "addPrimaryKey": {
                "tableName": name,
                "columnNames": ", ".join(column.value for column in table.primary_key.columns),
                "constraintName": primary_key_name(name),
            }
        },
    ]


def _add_column(table: TableName, column: Column, nullable: bool) -> list[dict[str, Any]]:
    return [
        {
            "addColumn": {
                "tableName": table.value,
                "columns": [_column(column, nullable)],
            }
        }
    ]


def _column(column: Column, nullable: bool) -> dict[str, Any]:
    definition: dict[str, Any] = {"name": column.name.value, "type": liquibase_type(column.type)}
    if not nullable:
        definition["constraints"] = {"nullable": False}
    return {"column": definition}


class LiquibaseYamlChangelogWriter:
    """Реализация контракта записи changelog."""

    def write(self, path: str, changelog: Changelog) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_changelog(changelog), encoding="utf-8")

    def remove(self, path: str) -> None:
        Path(path).unlink(missing_ok=True)


class LiquibaseYamlChangelogReader:
    """Реализация контракта чтения сводки changelog, построенного `forge generate`."""

    def exists(self, path: str) -> bool:
        return Path(path).is_file()

    def read(self, path: str) -> ChangelogSummary:
        try:
            document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
            raise ChangelogUnreadableError(f"changelog {path} не прочитать: {error}") from None
        try:
            return _summary(document)
        except (KeyError, TypeError, AttributeError) as error:
            raise ChangelogUnreadableError(
                f"changelog {path} не в формате forge generate: {error!r}"
            ) from None


def _summary(document: Any) -> ChangelogSummary:
    """Сводка по блокам `changes`; блоки `rollback` в неё не входят."""
    ids: list[str] = []
    tables: list[str] = []
    columns: list[tuple[str, str]] = []
    dropped_tables: list[str] = []
    dropped_columns: list[tuple[str, str]] = []
    paths: set[str] = set()
    for entry in document["databaseChangeLog"] or []:
        changeset = entry["changeSet"]
        ids.append(str(changeset["id"]))
        paths.add(str(changeset["logicalFilePath"]))
        for change in changeset["changes"]:
            if "createTable" in change:
                tables.append(str(change["createTable"]["tableName"]))
            elif "addColumn" in change:
                table = str(change["addColumn"]["tableName"])
                columns += [
                    (table, str(c["column"]["name"])) for c in change["addColumn"]["columns"]
                ]
            elif "dropTable" in change:
                dropped_tables.append(str(change["dropTable"]["tableName"]))
            elif "dropColumn" in change:
                dropped = change["dropColumn"]
                dropped_columns.append((str(dropped["tableName"]), str(dropped["columnName"])))
    if len(paths) > 1:
        raise TypeError(f"у changeset разные logicalFilePath: {sorted(paths)}")
    return ChangelogSummary(
        logical_file_path=paths.pop() if paths else None,
        changeset_ids=tuple(ids),
        tables=tuple(tables),
        columns=tuple(columns),
        dropped_tables=tuple(dropped_tables),
        dropped_columns=tuple(dropped_columns),
    )
