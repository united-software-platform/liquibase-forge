"""Таблица модели данных."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from forge.modeling.domain.column import Column
from forge.modeling.domain.identifier import ColumnName, TableName
from forge.modeling.domain.primary_key import PrimaryKey
from forge.modeling.domain.violation import ModelViolationError, Violation


@dataclass(frozen=True, eq=False)
class Table:
    """Таблица: идентичность по имени, колонки в порядке объявления, первичный ключ.

    Инварианты: хотя бы одна колонка, имена колонок уникальны, ключ ссылается на колонки
    таблицы, у колонок ключа нет явного `nullable: true`. Все нарушения таблицы сообщаются
    сразу, с путями относительно таблицы.
    """

    name: TableName
    columns: tuple[Column, ...]
    primary_key: PrimaryKey

    def __post_init__(self) -> None:
        violations = Table.violations_of(self.columns, self.primary_key)
        if violations:
            raise ModelViolationError(violations)

    @staticmethod
    def violations_of(columns: Sequence[Column], primary_key: PrimaryKey) -> list[Violation]:
        """Нарушения инвариантов таблицы из таких колонок и такого ключа."""
        violations: list[Violation] = []
        if not columns:
            violations.append(Violation("columns", "empty_columns", "таблица не содержит колонок"))
        positions: dict[ColumnName, int] = {}
        for position, column in enumerate(columns):
            if column.name in positions:
                violations.append(
                    Violation(
                        f"columns[{position}].name",
                        "duplicate_name",
                        f"колонка {column.name} уже объявлена в columns[{positions[column.name]}]",
                    )
                )
            else:
                positions[column.name] = position
        for position, name in enumerate(primary_key.columns):
            if name not in positions:
                violations.append(
                    Violation(
                        f"primary_key[{position}]",
                        "primary_key_unknown_column",
                        f"в таблице нет колонки {name}",
                    )
                )
        for position, column in enumerate(columns):
            if column.name in primary_key and column.nullable is True:
                violations.append(
                    Violation(
                        f"columns[{position}].nullable",
                        "primary_key_nullable",
                        f"колонка {column.name} входит в первичный ключ и не может допускать NULL",
                    )
                )
        return violations

    def column(self, name: ColumnName) -> Column:
        """Колонка по имени; отсутствие колонки — ошибка вызывающей стороны."""
        for column in self.columns:
            if column.name == name:
                return column
        raise KeyError(f"в таблице {self.name} нет колонки {name}")

    def is_nullable(self, name: ColumnName) -> bool:
        """Итоговая допустимость NULL: колонки ключа NOT NULL, без `nullable` — NULL допустим."""
        column = self.column(name)
        return name not in self.primary_key and column.nullable is not False

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Table) and other.name == self.name

    def __hash__(self) -> int:
        return hash(self.name)
