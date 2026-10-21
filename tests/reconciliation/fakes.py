"""Подставные реализации контрактов Сверки для тестов сценария и команды."""

from __future__ import annotations

from forge.reconciliation.application.contracts import ChangelogUnreadableError
from forge.reconciliation.domain.actual_schema import ActualSchema
from forge.reconciliation.domain.journal_check import ExpectedChangeSet, JournalRecord
from forge.shared.application.settings import DatabaseUnavailableError
from forge.shared.domain.target_database import TargetDatabase

FILE = "db/changelog/20261017-153000.yaml"
CHANGESET = ExpectedChangeSet("20261017-153000-01", "forge", FILE)


class FakeReconcileDatabase:
    def __init__(
        self,
        actual: ActualSchema,
        records: tuple[JournalRecord, ...] = (),
        available: bool = True,
    ) -> None:
        self.actual = actual
        self.journal = records
        self.available = available
        self.connected = False

    def read(self, database: TargetDatabase) -> ActualSchema:
        self._connect()
        return self.actual

    def records(self, database: TargetDatabase) -> tuple[JournalRecord, ...]:
        self._connect()
        return self.journal

    def _connect(self) -> None:
        self.connected = True
        if not self.available:
            raise DatabaseUnavailableError("БД недоступна")


class FakeChangesets:
    def __init__(self, readable: bool = True) -> None:
        self.readable = readable

    def read(self, path: str) -> tuple[ExpectedChangeSet, ...]:
        if not self.readable:
            raise ChangelogUnreadableError("нет файла")
        return (CHANGESET,)


EXECUTED = (JournalRecord("20261017-153000-01", "forge", FILE, "EXECUTED"),)
