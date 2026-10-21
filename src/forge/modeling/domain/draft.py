"""Черновик модели данных: значения нужного вида, ещё не проверенные инвариантами.

Черновик — вход фабрики модели в терминах домена, без следов формата файла. Вид значений
(строка, целое число, логическое значение) уже гарантирован тем, кто черновик собрал.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnDraft:
    """Колонка как объявлена: `None` у параметра или `nullable` — поле не задано."""

    name: str
    type: str
    nullable: bool | None = None
    length: int | None = None
    precision: int | None = None
    scale: int | None = None


@dataclass(frozen=True)
class TableDraft:
    """Таблица как объявлена; `position` — её индекс в списке `tables` файла модели."""

    position: int
    name: str
    columns: tuple[ColumnDraft, ...]
    primary_key: tuple[str, ...]


@dataclass(frozen=True)
class DataModelDraft:
    """Таблицы, прошедшие проверку вида значений, в порядке файла модели."""

    tables: tuple[TableDraft, ...]
