"""Сценарий закрытия операции с принятием модели в `db/`."""

from __future__ import annotations

from typing import Protocol

from forge.operation.application.accepted_state import (
    AcceptedFiles,
    AcceptedStateInterface,
    AttemptResultsReaderInterface,
)
from forge.operation.application.close_operation.input import CloseOperationInput
from forge.operation.application.close_operation.output import CloseOperationOutput
from forge.operation.application.operation_reading import OperationReadRepositoryInterface
from forge.operation.application.restore import restore
from forge.operation.application.views import operation_view
from forge.operation.domain.factory import OperationFactory
from forge.operation.domain.operation import FAILURE, OperationStatus
from forge.operation.domain.repository import OperationWriteRepositoryInterface


class CloseOperationUseCaseInterface(Protocol):
    """Закрыть операцию."""

    def execute(self, input: CloseOperationInput) -> CloseOperationOutput: ...


class CloseOperationUseCase:
    """Исход закрытия решает агрегат; при `success` файлы принимаются до записи статуса.

    Порядок «сначала `db/`, потом статус» не оставляет операцию `success` без принятых файлов:
    сбой принятия — `AcceptanceError`, статус остаётся прежним. Преждевременное закрытие —
    `OperationNotClosableError` агрегата.
    """

    def __init__(
        self,
        reads: OperationReadRepositoryInterface,
        writes: OperationWriteRepositoryInterface,
        results: AttemptResultsReaderInterface,
        accepted: AcceptedStateInterface,
        factory: OperationFactory,
    ) -> None:
        self._reads = reads
        self._writes = writes
        self._results = results
        self._accepted = accepted
        self._factory = factory

    def execute(self, input: CloseOperationInput) -> CloseOperationOutput:
        operation = restore(self._reads.get(input.operation_path), self._factory)
        rollbacks: dict[int, bool] = {}
        for attempt in operation.attempts:
            if attempt.verdict == FAILURE:
                summary = self._results.rollback(attempt.directory)
                rollbacks[attempt.number] = summary is not None and summary.verified
        outcome = operation.close(rollbacks)
        files: AcceptedFiles | None = None
        if outcome.status is OperationStatus.SUCCESS and outcome.accepted_attempt is not None:
            directory = operation.attempt(outcome.accepted_attempt).directory
            files = (
                self._accepted.accept(operation.stamp, directory)
                if outcome.changed
                else self._accepted.files(operation.stamp)
            )
        if outcome.changed:
            self._writes.save(operation)
        return CloseOperationOutput(
            operation_view(operation), outcome.accepted_attempt, files, outcome.changed
        )
