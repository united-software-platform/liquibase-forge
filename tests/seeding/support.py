"""Построители моделей и черновиков seed для тестов контекста Наполнение."""

from __future__ import annotations

from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.draft import ColumnDraft, DataModelDraft, ForeignKeyDraft, TableDraft
from forge.modeling.domain.factory import DataModelFactory
from forge.seeding.domain.draft import RawValue, RowDraft, ScalarKind, SeedDraft, SeedTableDraft


def model(*tables: TableDraft) -> DataModel:
    """Модель из черновиков таблиц; позиции проставляются по порядку."""
    numbered = tuple(
        TableDraft(position, t.name, t.columns, t.primary_key, t.unique, t.foreign_keys)
        for position, t in enumerate(tables)
    )
    return DataModelFactory().create(DataModelDraft(numbered))


def table(
    name: str,
    *columns: ColumnDraft,
    key: tuple[str, ...] = ("code",),
    unique: tuple[tuple[str, ...], ...] = (),
    foreign_keys: tuple[ForeignKeyDraft, ...] = (),
) -> TableDraft:
    return TableDraft(0, name, columns, key, unique, foreign_keys)


def reference(
    columns: tuple[str, ...], target: str, target_columns: tuple[str, ...]
) -> ForeignKeyDraft:
    return ForeignKeyDraft(columns, target, target_columns)


CODE = ColumnDraft("code", "string", length=32)

ORDER_STATUS = table(
    "order_status",
    CODE,
    ColumnDraft("title", "text", nullable=False),
    ColumnDraft("description", "text"),
    ColumnDraft("external_code", "string", length=16),
    unique=(("title",), ("external_code",)),
)

CATEGORY = table(
    "category",
    CODE,
    ColumnDraft("parent_code", "string", length=32),
    foreign_keys=(reference(("parent_code",), "category", ("code",)),),
)


def s(text: str) -> RawValue:
    return RawValue(ScalarKind.STRING, text)


def i(value: int) -> RawValue:
    return RawValue(ScalarKind.INTEGER, str(value))


def b(value: bool) -> RawValue:
    return RawValue(ScalarKind.BOOLEAN, "true" if value else "false")


def f(text: str) -> RawValue:
    return RawValue(ScalarKind.FLOAT, text)


def ts(text: str) -> RawValue:
    return RawValue(ScalarKind.TIMESTAMP, text)


NULL = RawValue(ScalarKind.NULL, "null")


def row(**values: RawValue) -> RowDraft:
    return RowDraft(tuple(values.items()))


def seed(*tables: tuple[str, tuple[RowDraft, ...]], excluded: tuple[str, ...] = ()) -> SeedDraft:
    return SeedDraft(
        tuple(SeedTableDraft(position, name, rows) for position, (name, rows) in enumerate(tables)),
        excluded,
    )
