"""Контракты прямого доступа к целевой БД: журнал Liquibase, наличие объектов, пересоздание."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from forge.migration.domain.target_database import TargetDatabase


class DatabaseUnavailableError(Exception):
    """К целевой БД или серверу не подключиться либо запрос не выполнен."""


@dataclass(frozen=True)
class JournalEntry:
    """Запись `DATABASECHANGELOG`: changeset, автор, файл и порядок исполнения."""

    id: str
    author: str
    filename: str
    order: int


class JournalReaderInterface(Protocol):
    """Чтение журнала Liquibase в порядке исполнения; нет таблицы журнала — пустой журнал."""

    def entries(self, database: TargetDatabase) -> tuple[JournalEntry, ...]: ...


class SchemaProbeInterface(Protocol):
    """Есть ли таблица или колонка в схеме `public`."""

    def table_exists(self, database: TargetDatabase, table: str) -> bool: ...

    def column_exists(self, database: TargetDatabase, table: str, column: str) -> bool: ...


class DatabaseRecreatorInterface(Protocol):
    """Удалить целевую БД и создать её заново пустой."""

    def recreate(self, database: TargetDatabase) -> None: ...
