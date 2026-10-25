"""Подставные реализации контрактов сверки seed для тестов сценария и команды."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import yaml

from forge.modeling.application.load_model.use_case import LoadModelUseCase
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.domain.identifier import TableName
from forge.modeling.domain.table import Table
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader
from forge.reconciliation.domain.journal_check import JournalRecord
from forge.seeding.application.reconcile_seed.use_case import (
    ReconcileSeedDependencies,
    ReconcileSeedUseCase,
)
from forge.seeding.domain.draft import RawValue, RowDraft, ScalarKind, SeedDraft, SeedTableDraft
from forge.seeding.domain.factory import SeedFactory
from forge.seeding.domain.seed import SeedRow
from forge.seeding.infrastructure.yaml_reader import YamlSeedDraftReader
from forge.shared.application.result_writer import ResultWriterInterface
from forge.shared.application.settings import DatabaseUnavailableError
from forge.shared.domain.target_database import TargetDatabase
from tests.migration.fakes import FakeSettings
from tests.reconciliation.fakes import EXECUTED, FakeChangesets

MODEL = """version: 1
tables:
  - name: order_status
    columns:
      - {name: code, type: string, length: 32}
      - {name: title, type: text, nullable: false}
      - {name: description, type: text}
    primary_key: [code]
  - name: legacy_status
    columns:
      - {name: code, type: string, length: 32}
    primary_key: [code]
  - name: customer
    columns:
      - {name: id, type: bigint}
    primary_key: [id]
"""

SEED = """version: 1
tables:
  - name: order_status
    rows:
      - {code: draft, title: Черновик}
      - {code: paid, title: Оплачен}
"""

ACCEPTED = """version: 1
tables:
  - name: order_status
    rows:
      - {code: draft, title: Черновик}
  - name: legacy_status
    rows:
      - {code: old}
"""


class FakeDatabase:
    """Строки таблиц и журнал БД.

    Строки задаются текстом в формате seed; чтение возвращает только запрошенные таблицы
    и запоминает их имена.
    """

    def __init__(
        self,
        rows_yaml: str,
        records: tuple[JournalRecord, ...] = EXECUTED,
        available: bool = True,
    ) -> None:
        self.rows_yaml = rows_yaml
        self.journal = records
        self.available = available
        self.connected = False
        self.requested: list[str] = []

    def rows(
        self, database: TargetDatabase, tables: Sequence[Table]
    ) -> dict[TableName, tuple[SeedRow, ...]]:
        self._connect()
        self.requested = [table.name.value for table in tables]
        names = set(self.requested)
        draft = yaml.safe_load(self.rows_yaml)
        kept = [entry for entry in draft["tables"] if entry["name"] in names]
        drafts = SeedDraft(
            tuple(
                SeedTableDraft(
                    position,
                    entry["name"],
                    tuple(
                        RowDraft(tuple((k, _raw(v)) for k, v in values.items()))
                        for values in entry["rows"]
                    ),
                )
                for position, entry in enumerate(kept)
            )
        )
        actual = SeedFactory().create(DataModel(tuple(tables)), drafts)
        return {
            table.name: actual.table(table.name).rows if actual.has_table(table.name) else ()
            for table in tables
        }

    def records(self, database: TargetDatabase) -> tuple[JournalRecord, ...]:
        self._connect()
        return self.journal

    def _connect(self) -> None:
        self.connected = True
        if not self.available:
            raise DatabaseUnavailableError("БД недоступна")


def _raw(value: object) -> RawValue:
    if value is None:
        return RawValue(ScalarKind.NULL, "null")
    if isinstance(value, bool):
        return RawValue(ScalarKind.BOOLEAN, "true" if value else "false")
    if isinstance(value, int):
        return RawValue(ScalarKind.INTEGER, str(value))
    return RawValue(ScalarKind.STRING, str(value))


def use_case(
    tmp: Path,
    db: FakeDatabase,
    writer: ResultWriterInterface,
    settings: FakeSettings | None = None,
    changesets: FakeChangesets | None = None,
) -> ReconcileSeedUseCase:
    return ReconcileSeedUseCase(
        ReconcileSeedDependencies(
            settings=settings or FakeSettings(),
            models=LoadModelUseCase(YamlModelDraftReader(), DataModelFactory()),
            seeds=YamlSeedDraftReader(),
            changesets=changesets or FakeChangesets(),
            rows=db,
            journal=db,
            writer=writer,
            factory=SeedFactory(),
        )
    )


def files(tmp: Path, seed: str = SEED, accepted: str | None = ACCEPTED) -> dict[str, str]:
    """Файлы попытки во временном каталоге: модель, seed, принятый seed и путь changelog."""
    (tmp / "model.yaml").write_text(MODEL, encoding="utf-8")
    (tmp / "attempt-1").mkdir(exist_ok=True)
    (tmp / "attempt-1" / "seed.yaml").write_text(seed, encoding="utf-8")
    if accepted is not None:
        (tmp / "accepted-seed.yaml").write_text(accepted, encoding="utf-8")
    return {
        "model": str(tmp / "model.yaml"),
        "seed": str(tmp / "attempt-1" / "seed.yaml"),
        "accepted_seed": str(tmp / "accepted-seed.yaml"),
        "changelog": str(tmp / "attempt-1" / "changelog.yaml"),
    }
