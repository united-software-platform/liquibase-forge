"""Контракты принятого состояния `db/` и результатов попыток."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AcceptanceError(Exception):
    """Принять модель и changelog в `db/` не удалось: нет файлов попытки или записи."""


@dataclass(frozen=True)
class AcceptedFiles:
    """Файлы принятого состояния операции."""

    model: str
    changelog: str
    master: str


class AcceptedStateInterface(Protocol):
    """Принятое состояние проекта."""

    def accept(self, stamp: str, attempt_directory: str) -> AcceptedFiles:
        """Принять модель и changelog попытки; повторное принятие ничего не меняет."""
        ...

    def files(self, stamp: str) -> AcceptedFiles:
        """Пути принятых файлов операции."""
        ...


@dataclass(frozen=True)
class DiscrepancySummary:
    """Расхождение сверки попытки, как его записал `forge reconcile`."""

    kind: str
    table: str | None
    column: str | None
    changeset: str | None
    expected: str
    actual: str
    message: str


@dataclass(frozen=True)
class ReconcileSummary:
    """Итог сверки попытки из `reconcile.json`."""

    verdict: str
    discrepancies: tuple[DiscrepancySummary, ...]


@dataclass(frozen=True)
class RollbackSummary:
    """Итог отката попытки из `rollback.json`."""

    action: str
    rolled_back: int
    verified: bool
    fallback_reason: str | None


@dataclass(frozen=True)
class DestructiveChange:
    """Удаление итогового changelog: таблица и колонка; у удалённой таблицы колонка — `None`."""

    table: str
    column: str | None


class AttemptResultsReaderInterface(Protocol):
    """Результаты попытки: сверка и откат в её каталоге, удаления её changelog."""

    def reconcile(self, attempt_directory: str) -> ReconcileSummary | None:
        """Итог сверки; нет файла — `None`."""
        ...

    def rollback(self, attempt_directory: str) -> RollbackSummary | None:
        """Итог отката; нет файла — `None`."""
        ...

    def destructive(self, changelog: str) -> tuple[DestructiveChange, ...]:
        """Удаления changelog; нет файла или он не читается — пустой перечень."""
        ...
