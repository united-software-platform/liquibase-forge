"""Выходной контракт сценария отчёта: итог операции для LLM."""

from __future__ import annotations

from dataclasses import dataclass

from forge.operation.application.accepted_state import (
    AcceptedFiles,
    ReconcileSummary,
    RollbackSummary,
)
from forge.operation.application.views import OperationView


@dataclass(frozen=True)
class AttemptReport:
    """Попытка в отчёте: вердикт, артефакты, итоги сверки и отката."""

    number: int
    verdict: str | None
    backlog: str | None
    directory: str
    model: str
    changelog: str
    reconcile: ReconcileSummary | None
    rollback: RollbackSummary | None


@dataclass(frozen=True)
class BuildReportOutput:
    """Отчёт: операция, итоговые модель и changelog, попытки, беклоги, файлы для коммита.

    `commit_files` — `None` у открытой операции; у закрытой — принятые файлы при `success`
    и каталоги следа: операции и беклогов начатых попыток.
    """

    operation: OperationView
    model: str | None
    changelog: str | None
    attempts: tuple[AttemptReport, ...]
    backlogs: tuple[str, ...]
    accepted: AcceptedFiles | None
    commit_files: tuple[str, ...] | None
