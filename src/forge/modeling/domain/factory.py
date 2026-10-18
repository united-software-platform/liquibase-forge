"""Фабрика модели данных: строит агрегат из черновика или сообщает все нарушения сразу."""

from __future__ import annotations

from forge.modeling.domain.column import Column
from forge.modeling.domain.column_type import ColumnType
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.draft import ColumnDraft, DataModelDraft, TableDraft
from forge.modeling.domain.identifier import ColumnName, TableName
from forge.modeling.domain.primary_key import PrimaryKey
from forge.modeling.domain.table import Table
from forge.modeling.domain.violation import ModelViolationError, Violation


class DataModelFactory:
    """Строит модель снизу вверх: колонки, ключ, таблицы, агрегат.

    Нарушение одного элемента не останавливает проверку остальных: фабрика собирает нарушения
    каждого уровня с путями от корня файла модели и бросает их одним исключением. Колонка
    строится, только если корректны её имя и тип; инварианты таблицы проверяются, только если
    корректны все её колонки и ключ. Уникальность имён таблиц проверяется по всем таблицам
    с корректным именем.
    """

    def create(self, draft: DataModelDraft) -> DataModel:
        names: list[tuple[int, TableName]] = []
        tables: list[Table] = []
        violations: dict[int, list[Violation]] = {}
        for table_draft in draft.tables:
            table, table_violations, name = self._table(table_draft)
            violations[table_draft.position] = table_violations
            if name is not None:
                names.append((table_draft.position, name))
            if table is not None:
                tables.append(table)
        # Повтор имени — нарушение поля `name`, поэтому оно идёт первым среди нарушений таблицы
        for position, duplicate in DataModel.duplicate_names(names).items():
            violations[position].insert(0, duplicate)
        collected = [
            violation
            for table_draft in draft.tables
            for violation in violations[table_draft.position]
        ]
        if collected:
            raise ModelViolationError(collected)
        return DataModel(tuple(tables))

    def _table(self, draft: TableDraft) -> tuple[Table | None, list[Violation], TableName | None]:
        prefix = f"tables[{draft.position}]"
        violations: list[Violation] = []

        name: TableName | None = None
        try:
            name = TableName(draft.name)
        except ModelViolationError as error:
            violations += error.under("name").violations

        columns: list[Column] = []
        for index, column_draft in enumerate(draft.columns):
            try:
                columns.append(self._column(column_draft))
            except ModelViolationError as error:
                violations += error.under(f"columns[{index}]").violations

        key, key_violations = self._primary_key(draft.primary_key)
        violations += key_violations

        table: Table | None = None
        if key is not None and len(columns) == len(draft.columns):
            violations += Table.violations_of(columns, key)
            if name is not None and not violations:
                table = Table(name, tuple(columns), key)
        return table, [violation.under(prefix) for violation in violations], name

    @staticmethod
    def _column(draft: ColumnDraft) -> Column:
        violations: list[Violation] = []
        name: ColumnName | None = None
        try:
            name = ColumnName(draft.name)
        except ModelViolationError as error:
            violations += error.under("name").violations
        column_type: ColumnType | None = None
        try:
            column_type = ColumnType.of(
                draft.type, length=draft.length, precision=draft.precision, scale=draft.scale
            )
        except ModelViolationError as error:
            violations += error.violations
        if name is None or column_type is None:
            raise ModelViolationError(violations)
        return Column(name, column_type, draft.nullable)

    @staticmethod
    def _primary_key(names: tuple[str, ...]) -> tuple[PrimaryKey | None, list[Violation]]:
        columns: list[ColumnName] = []
        violations: list[Violation] = []
        for position, value in enumerate(names):
            try:
                columns.append(ColumnName(value))
            except ModelViolationError:
                # Колонки с некорректным именем в таблице быть не может
                violations.append(
                    Violation(
                        f"primary_key[{position}]",
                        "primary_key_unknown_column",
                        f"в таблице нет колонки {value!r}",
                    )
                )
        if violations:
            return None, violations
        try:
            return PrimaryKey(tuple(columns)), []
        except ModelViolationError as error:
            return None, list(error.under("primary_key").violations)
