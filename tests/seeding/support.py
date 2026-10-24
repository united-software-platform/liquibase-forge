"""Построители моделей и черновиков seed для тестов контекста Наполнение."""

from __future__ import annotations

from pathlib import Path

from forge.modeling.application.load_model.input import LoadModelInput
from forge.modeling.application.load_model.use_case import LoadModelUseCase
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.draft import ColumnDraft, DataModelDraft, ForeignKeyDraft, TableDraft
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader
from forge.seeding.domain.draft import RawValue, RowDraft, ScalarKind, SeedDraft, SeedTableDraft
from forge.seeding.domain.factory import SeedFactory
from forge.seeding.domain.seed import Seed
from forge.seeding.infrastructure.yaml_reader import YamlSeedDraftReader


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


MIGRATION_EXAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "seed" / "migration"
"""Фикстурный пример changelog данных: модель, принятый seed, seed попытки и эталон."""

EXAMPLE_STAMP = "20261025-101500"


def migration_example() -> tuple[Seed, Seed]:
    """Принятый seed и seed попытки фикстурного примера, проверенные по его модели."""
    loaded = LoadModelUseCase(YamlModelDraftReader(), DataModelFactory()).execute(
        LoadModelInput(str(MIGRATION_EXAMPLE / "model.yaml"))
    )
    reader = YamlSeedDraftReader()

    def load(name: str) -> Seed:
        return SeedFactory().create(loaded.model, reader.read(str(MIGRATION_EXAMPLE / name)).draft)

    return load("accepted.yaml"), load("attempt.yaml")
