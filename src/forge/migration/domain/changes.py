"""Изменения схемы, которые выражает changelog, и неподдерживаемые изменения модели."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from forge.modeling.domain.column import Column
from forge.modeling.domain.identifier import TableName
from forge.modeling.domain.table import Table


@dataclass(frozen=True)
class CreateTable:
    """Новая таблица целиком: колонки, NOT NULL и первичный ключ."""

    table: Table


@dataclass(frozen=True)
class AddColumn:
    """Новая колонка существующей таблицы с итоговой допустимостью NULL."""

    table: TableName
    column: Column
    nullable: bool


@dataclass(frozen=True)
class DropTable:
    """Удаляемая таблица целиком; принятое определение нужно для отката."""

    table: Table


@dataclass(frozen=True)
class DropColumn:
    """Удаляемая колонка существующей таблицы; принятое определение нужно для отката."""

    table: TableName
    column: Column
    nullable: bool


SchemaChange = CreateTable | AddColumn | DropTable | DropColumn


@dataclass(frozen=True)
class UnsupportedChange:
    """Изменение модели, которое changelog не выражает: смена типа, NULL или первичного ключа."""

    code: str
    table: str
    column: str | None
    message: str


class UnsupportedChangeError(Exception):
    """Модель попытки требует неподдерживаемых изменений: перечислены все."""

    def __init__(self, changes: Iterable[UnsupportedChange]) -> None:
        self.changes: tuple[UnsupportedChange, ...] = tuple(changes)
        if not self.changes:
            raise ValueError("UnsupportedChangeError требует хотя бы одного изменения")
        super().__init__("; ".join(change.message for change in self.changes))
