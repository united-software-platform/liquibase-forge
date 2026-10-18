"""Изменения схемы, которые выражает changelog, и неаддитивные изменения модели."""

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


SchemaChange = CreateTable | AddColumn


@dataclass(frozen=True)
class NonAdditiveChange:
    """Изменение модели, которое changelog первой поставки не выражает."""

    code: str
    table: str
    column: str | None
    message: str


class NonAdditiveChangeError(Exception):
    """Модель попытки требует неаддитивных изменений: перечислены все."""

    def __init__(self, changes: Iterable[NonAdditiveChange]) -> None:
        self.changes: tuple[NonAdditiveChange, ...] = tuple(changes)
        if not self.changes:
            raise ValueError("NonAdditiveChangeError требует хотя бы одного изменения")
        super().__init__("; ".join(change.message for change in self.changes))
