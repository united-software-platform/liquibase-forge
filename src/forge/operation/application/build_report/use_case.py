"""Сценарий итогового отчёта операции."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Protocol

from forge.operation.application.accepted_state import (
    AcceptedStateInterface,
    AttemptResultsReaderInterface,
)
from forge.operation.application.build_report.input import BuildReportInput
from forge.operation.application.build_report.output import AttemptReport, BuildReportOutput
from forge.operation.application.operation_reading import OperationReadRepositoryInterface
from forge.operation.application.restore import restore
from forge.operation.application.views import operation_view
from forge.operation.domain.factory import OperationFactory
from forge.operation.domain.operation import OperationStatus

MODEL = "model.yaml"
CHANGELOG = "changelog.yaml"


class BuildReportUseCaseInterface(Protocol):
    """Собрать итоговый отчёт операции."""

    def execute(self, input: BuildReportInput) -> BuildReportOutput: ...


class BuildReportUseCase:
    """Отчёт без побочных эффектов: беклог, результаты попыток и принятые файлы.

    В отчёт входят попытки, которые начались: с вердиктом или порождённым беклогом.
    Итоговые модель и changelog — принятые файлы корня принятого состояния при `success`,
    иначе файлы последней начатой попытки. Файлы для коммита называются только у закрытой
    операции: след операции, а при `success` — и принятые файлы.
    """

    def __init__(
        self,
        reads: OperationReadRepositoryInterface,
        results: AttemptResultsReaderInterface,
        accepted: AcceptedStateInterface,
        factory: OperationFactory,
    ) -> None:
        self._reads = reads
        self._results = results
        self._accepted = accepted
        self._factory = factory

    def execute(self, input: BuildReportInput) -> BuildReportOutput:
        operation = restore(self._reads.get(input.operation_path), self._factory)
        attempts = tuple(
            AttemptReport(
                number=a.number,
                verdict=a.verdict,
                backlog=a.backlog,
                directory=a.directory,
                model=f"{a.directory}/{MODEL}",
                changelog=f"{a.directory}/{CHANGELOG}",
                reconcile=self._results.reconcile(a.directory),
                rollback=self._results.rollback(a.directory),
            )
            for a in operation.attempts
            if a.verdict is not None or a.backlog is not None
        )
        accepted = (
            self._accepted.files(operation.stamp)
            if operation.status is OperationStatus.SUCCESS
            else None
        )
        model: str | None
        changelog: str | None
        if accepted is not None:
            model, changelog = accepted.model, accepted.changelog
        elif attempts:
            model, changelog = attempts[-1].model, attempts[-1].changelog
        else:
            model = changelog = None
        backlogs = (operation.path, *(a.backlog for a in attempts if a.backlog is not None))
        commit_files: tuple[str, ...] | None = None
        if operation.status in (OperationStatus.SUCCESS, OperationStatus.FAILURE):
            trail = tuple(_directory(backlog) for backlog in backlogs)
            files = (accepted.model, accepted.changelog, accepted.master) if accepted else ()
            commit_files = (*files, *trail)
        return BuildReportOutput(
            operation=operation_view(operation),
            model=model,
            changelog=changelog,
            attempts=attempts,
            backlogs=backlogs,
            accepted=accepted,
            commit_files=commit_files,
        )


def _directory(backlog: str) -> str:
    """Каталог беклога в следе с завершающим `/`: коммитится целиком, с артефактами попыток."""
    return f"{PurePosixPath(backlog).parent.as_posix()}/"
