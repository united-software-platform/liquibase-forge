"""Фактическая схема целевой БД, полученная интроспекцией каталога PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass

from forge.modeling.domain.column_type import ColumnType


@dataclass(frozen=True)
class ActualColumn:
    """Колонка в БД: тип модели, если тип PostgreSQL входит в формат, и исходное имя типа."""

    name: str
    type: ColumnType | None
    database_type: str
    nullable: bool

    @property
    def type_text(self) -> str:
        """Тип в записи формата либо исходный тип PostgreSQL, если формат его не знает."""
        return str(self.type) if self.type is not None else self.database_type


@dataclass(frozen=True)
class ActualTable:
    """Таблица в БД: колонки в порядке каталога и первичный ключ, если он есть."""

    name: str
    columns: tuple[ActualColumn, ...]
    primary_key: tuple[str, ...] | None

    def column(self, name: str) -> ActualColumn | None:
        return next((column for column in self.columns if column.name == name), None)


@dataclass(frozen=True)
class ActualSchema:
    """Таблицы схемы `public` без таблиц журнала Liquibase."""

    tables: tuple[ActualTable, ...]

    def table(self, name: str) -> ActualTable | None:
        return next((table for table in self.tables if table.name == name), None)
