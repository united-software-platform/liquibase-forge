"""Подставные реализации контрактов Миграции для тестов сценариев."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from forge.migration.application.changelog_storage import (
    ChangelogSummary,
    ChangelogUnreadableError,
    RowRef,
)
from forge.migration.application.database import JournalEntry
from forge.migration.application.liquibase_gateway import GatewayResult, GatewayUnavailableError
from forge.migration.application.operation_record import OperationRecord
from forge.migration.domain.stamp import OperationStamp
from forge.shared.application.settings import DatabaseCredentials
from forge.shared.domain.target_database import (
    TargetDatabase,
    TestDatabaseAllowlist,
    parse_allowlist,
)

TARGET = TargetDatabase("lbfr-db-test", 5432, "t_0001")


class FakeSettings:
    def __init__(
        self, allowlist: str = "lbfr-db-test:5432/*", target: TargetDatabase = TARGET
    ) -> None:
        self._allowlist = allowlist
        self._target = target

    def target(self) -> TargetDatabase:
        return self._target

    def credentials(self) -> DatabaseCredentials:
        return DatabaseCredentials("forge_test", "forge_test")

    def allowlist(self) -> TestDatabaseAllowlist:
        return parse_allowlist(self._allowlist)


class FakeGateway:
    """Шлюз, отвечающий заданными исходами по очереди; запоминает вызовы."""

    def __init__(self, *outcomes: int | GatewayUnavailableError) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, str, TargetDatabase, int | None]] = []

    def update(self, changelog: str, database: TargetDatabase) -> GatewayResult:
        self.calls.append(("update", changelog, database, None))
        return self._next()

    def rollback(self, changelog: str, database: TargetDatabase, count: int) -> GatewayResult:
        self.calls.append(("rollback", changelog, database, count))
        return self._next()

    def _next(self) -> GatewayResult:
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, GatewayUnavailableError):
            raise outcome
        stderr = "" if outcome == 0 else "ERROR: liquibase"
        return GatewayResult(f"req-{len(self.calls)}", outcome, "out", stderr)


class FakeWriter:
    def __init__(self) -> None:
        self.documents: dict[str, Mapping[str, Any]] = {}

    def write(self, path: str, document: Mapping[str, Any]) -> None:
        self.documents[path] = document


LOGICAL = "db/changelog/20261017-153000.yaml"
ACCEPTED = "db/changelog/20261001-090000.yaml"
SUMMARY = ChangelogSummary(
    LOGICAL,
    ("20261017-153000-01", "20261017-153000-02", "20261017-153000-03"),
    ("invoice", "payment"),
    (("customer", "phone"),),
)


@dataclass
class FakeDatabase:
    """Подставная БД: журнал и объекты схемы, которые меняют шлюз и пересоздание."""

    journal: list[JournalEntry] = field(default_factory=list)
    tables: set[str] = field(default_factory=set)
    columns: set[tuple[str, str]] = field(default_factory=set)
    constraints: set[tuple[str, str, str]] = field(default_factory=set)
    rollback_code: int = 0
    master_exists: bool = False
    summary: ChangelogSummary | None = SUMMARY
    row_counts: dict[RowRef, int] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def apply_attempt(self, count: int) -> None:
        """Записать в журнал первые `count` changeset попытки и их объекты."""
        accepted = JournalEntry("20261001-090000-01", "forge", ACCEPTED, 1)
        self.journal = [accepted] + [
            JournalEntry(SUMMARY.changeset_ids[i], "forge", LOGICAL, i + 2) for i in range(count)
        ]
        self.tables = {"customer"} | set(SUMMARY.tables[: min(count, 2)])
        self.columns = {("customer", "id")} | ({("customer", "phone")} if count == 3 else set())

    # Журнал, схема и пересоздание
    def entries(self, database: TargetDatabase) -> tuple[JournalEntry, ...]:
        return tuple(self.journal)

    def table_exists(self, database: TargetDatabase, table: str) -> bool:
        return table in self.tables

    def column_exists(self, database: TargetDatabase, table: str, column: str) -> bool:
        return (table, column) in self.columns

    def constraint_exists(self, database: TargetDatabase, table: str, name: str, kind: str) -> bool:
        return (kind, table, name) in self.constraints

    def count_rows(self, database: TargetDatabase, row: RowRef) -> int:
        return self.row_counts.get(row, 0)

    def recreate(self, database: TargetDatabase) -> None:
        self.calls.append("recreate")
        self.journal, self.tables, self.columns = [], set(), set()

    # Шлюз
    def update(self, changelog: str, database: TargetDatabase) -> GatewayResult:
        self.calls.append(f"update {changelog}")
        self.journal = [JournalEntry("20261001-090000-01", "forge", ACCEPTED, 1)]
        self.tables, self.columns = {"customer"}, {("customer", "id")}
        return GatewayResult("req", 0, "", "")

    def rollback(self, changelog: str, database: TargetDatabase, count: int) -> GatewayResult:
        self.calls.append(f"rollback {count}")
        if self.rollback_code != 0:
            return GatewayResult("req", self.rollback_code, "", "ERROR")
        self.journal = self.journal[:-count]
        self.tables = {"customer"}
        self.columns = {("customer", "id")}
        return GatewayResult("req", 0, "", "")

    # Чтение changelog
    def read(self, path: str) -> ChangelogSummary:
        if self.summary is None:
            raise ChangelogUnreadableError("нет файла")
        return self.summary

    def exists(self, path: str) -> bool:
        return self.master_exists


class FakeOperations:
    def __init__(self, verdict: str | None) -> None:
        self._verdict = verdict

    def read(self, path: str) -> OperationRecord:
        return OperationRecord(
            OperationStamp("20261017-153000"), {1: self._verdict, 2: None, 3: None}, "trail"
        )
