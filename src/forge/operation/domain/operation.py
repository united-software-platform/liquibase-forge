"""Операция Liquibase Forge — корень агрегата контекста Операция."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

ATTEMPT_LIMIT = 3
SUCCESS = "success"
FAILURE = "failure"


class OperationStatus(StrEnum):
    """Статус операции: открыта (`running`, `stopped`) либо закрыта (`success`, `failure`)."""

    RUNNING = "running"
    STOPPED = "stopped"
    SUCCESS = "success"
    FAILURE = "failure"

    @property
    def closed(self) -> bool:
        return self in (OperationStatus.SUCCESS, OperationStatus.FAILURE)


class OperationTransitionError(Exception):
    """Переход статуса недопустим: операция не меняется."""


class OperationClosedError(OperationTransitionError):
    """Операция уже закрыта."""


class OperationNotStoppedError(OperationTransitionError):
    """Продолжить можно только остановленную операцию."""


class OperationNotClosableError(OperationTransitionError):
    """Закрывать операцию рано: нет ни подтверждённой попытки, ни трёх неудач с откатом."""


@dataclass(frozen=True)
class Attempt:
    """Попытка: номер, вердикт сверки, беклог попытки и каталог её артефактов."""

    number: int
    verdict: str | None
    backlog: str | None
    directory: str

    @property
    def used(self) -> bool:
        return self.verdict is not None


@dataclass(frozen=True)
class CloseOutcome:
    """Исход закрытия: статус, принятая попытка при `success` и было ли закрытие сейчас."""

    status: OperationStatus
    accepted_attempt: int | None
    changed: bool


class Operation:
    """Операция: намерение, режим, статус, причина остановки и три попытки.

    Статус меняют только операции агрегата: `stop`, `resume`, `close`. Вердикты попыток
    записывает исполнение беклога, агрегат их только читает.
    """

    def __init__(
        self,
        path: str,
        stamp: str,
        intent: str,
        mode: str,
        status: OperationStatus,
        stop_reason: str | None,
        attempts: tuple[Attempt, ...],
    ) -> None:
        self.path = path
        self.stamp = stamp
        self.intent = intent
        self.mode = mode
        self._status = status
        self._stop_reason = stop_reason
        self.attempts = attempts

    @property
    def status(self) -> OperationStatus:
        return self._status

    @property
    def stop_reason(self) -> str | None:
        return self._stop_reason

    @property
    def confirmed_attempt(self) -> Attempt | None:
        """Первая попытка с вердиктом `success`."""
        return next((a for a in self.attempts if a.verdict == SUCCESS), None)

    @property
    def used_attempts(self) -> int:
        return sum(1 for attempt in self.attempts if attempt.used)

    def attempt(self, number: int) -> Attempt:
        return next(a for a in self.attempts if a.number == number)

    def stop(self, reason: str) -> None:
        """Остановить открытую операцию; повторная остановка заменяет причину."""
        if self._status.closed:
            raise OperationClosedError(f"операция закрыта со статусом {self._status}")
        self._status = OperationStatus.STOPPED
        self._stop_reason = reason

    def resume(self) -> None:
        """Продолжить остановленную операцию."""
        if self._status.closed:
            raise OperationClosedError(f"операция закрыта со статусом {self._status}")
        if self._status is not OperationStatus.STOPPED:
            raise OperationNotStoppedError(f"операция не остановлена: статус {self._status}")
        self._status = OperationStatus.RUNNING
        self._stop_reason = None

    def close(self, rollbacks: Mapping[int, bool]) -> CloseOutcome:
        """Закрыть операцию по вердиктам попыток и подтверждению откатов.

        `rollbacks` — подтверждён ли откат попытки по её `rollback.json`. Повторное закрытие
        закрытой операции ничего не меняет и сообщает прежний исход.
        """
        confirmed = self.confirmed_attempt
        if self._status.closed:
            number = (
                confirmed.number if self._status is OperationStatus.SUCCESS and confirmed else None
            )
            return CloseOutcome(self._status, number, changed=False)
        if self._status is OperationStatus.STOPPED:
            raise OperationNotClosableError("операция остановлена: сначала forge resume")
        if confirmed is not None:
            self._status = OperationStatus.SUCCESS
            return CloseOutcome(self._status, confirmed.number, changed=True)
        failed = [a for a in self.attempts if a.verdict == FAILURE]
        unconfirmed = [a.number for a in failed if not rollbacks.get(a.number, False)]
        if len(failed) == ATTEMPT_LIMIT and not unconfirmed:
            self._status = OperationStatus.FAILURE
            return CloseOutcome(self._status, None, changed=True)
        reason = (
            f"откат не подтверждён у попыток {', '.join(map(str, unconfirmed))}"
            if unconfirmed
            else f"подтверждённой попытки нет, неуспешных попыток {len(failed)} из {ATTEMPT_LIMIT}"
        )
        raise OperationNotClosableError(f"закрывать рано: {reason}")
