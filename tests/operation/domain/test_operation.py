"""Агрегат операции: переходы статуса и закрытие."""

from __future__ import annotations

import pytest

from forge.operation.domain.factory import OperationFactory, OperationRestoreError
from forge.operation.domain.operation import (
    Operation,
    OperationClosedError,
    OperationDropConsentError,
    OperationNotClosableError,
    OperationNotStoppedError,
    OperationStatus,
)

FAILED_ROLLBACKS = {1: True, 2: True, 3: True}


def _operation(
    status: str = "running",
    verdicts: tuple[str | None, str | None, str | None] = (None, None, None),
) -> Operation:
    return OperationFactory().restore(
        path="backlog/forge-model/20261017-153000/tasks.md",
        stamp="20261017-153000",
        intent="Таблица клиентов",
        mode="auto",
        status=status,
        stop_reason=None,
        attempts=[
            (verdict, None, f"backlog/forge-model/20261017-153000/attempt-{n}")
            for n, verdict in enumerate(verdicts, start=1)
        ],
    )


def test_stop_and_resume() -> None:
    operation = _operation()

    operation.stop("раннер недоступен")
    assert (operation.status, operation.stop_reason) == (
        OperationStatus.STOPPED,
        "раннер недоступен",
    )

    operation.resume()
    assert (operation.status, operation.stop_reason) == (OperationStatus.RUNNING, None)


def test_repeated_stop_replaces_reason() -> None:
    operation = _operation()
    operation.stop("первая")

    operation.stop("вторая")

    assert operation.stop_reason == "вторая"


def test_resume_of_running_operation() -> None:
    with pytest.raises(OperationNotStoppedError):
        _operation().resume()


@pytest.mark.parametrize("status", ["success", "failure"])
def test_closed_operation_is_not_stopped_or_resumed(status: str) -> None:
    operation = _operation(
        status, ("success", None, None) if status == "success" else ("failure",) * 3
    )

    with pytest.raises(OperationClosedError):
        operation.stop("x")
    with pytest.raises(OperationClosedError):
        operation.resume()


def test_close_with_confirmed_attempt() -> None:
    operation = _operation(verdicts=("failure", "success", None))

    outcome = operation.close({1: True})

    assert (outcome.status, outcome.accepted_attempt, outcome.changed) == (
        OperationStatus.SUCCESS,
        2,
        True,
    )
    assert operation.status is OperationStatus.SUCCESS
    assert operation.used_attempts == 2
    assert operation.confirmed_attempt is not None and operation.confirmed_attempt.number == 2


def test_close_after_three_failures_with_confirmed_rollbacks() -> None:
    operation = _operation(verdicts=("failure", "failure", "failure"))

    outcome = operation.close(FAILED_ROLLBACKS)

    assert (outcome.status, outcome.accepted_attempt) == (OperationStatus.FAILURE, None)


def test_close_after_three_failures_with_unconfirmed_rollback() -> None:
    operation = _operation(verdicts=("failure", "failure", "failure"))

    with pytest.raises(OperationNotClosableError, match="попыток 2"):
        operation.close({1: True, 2: False, 3: True})

    assert operation.status is OperationStatus.RUNNING


def test_premature_close() -> None:
    operation = _operation(verdicts=("failure", None, None))

    with pytest.raises(OperationNotClosableError, match="1 из 3"):
        operation.close({1: True})

    assert operation.status is OperationStatus.RUNNING


def test_stopped_operation_is_not_closed() -> None:
    operation = _operation(verdicts=("success", None, None))
    operation.stop("отказ владельца")

    with pytest.raises(OperationNotClosableError, match="resume"):
        operation.close({})


def test_repeated_close_reports_previous_outcome() -> None:
    operation = _operation("success", ("success", None, None))

    outcome = operation.close({})

    assert (outcome.status, outcome.accepted_attempt, outcome.changed) == (
        OperationStatus.SUCCESS,
        1,
        False,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("stamp", "2026-10-17"), ("mode", "manual"), ("status", "paused")],
)
def test_restore_rejects_unknown_values(field: str, value: str) -> None:
    values = {
        "path": "tasks.md",
        "stamp": "20261017-153000",
        "intent": "x",
        "mode": "auto",
        "status": "running",
        "stop_reason": None,
        "attempts": [(None, None, "a")] * 3,
        field: value,
    }

    with pytest.raises(OperationRestoreError):
        OperationFactory().restore(**values)  # type: ignore[arg-type]


def test_restore_rejects_unknown_verdict() -> None:
    with pytest.raises(OperationRestoreError):
        _operation(verdicts=("maybe", None, None))


def _with_mode(mode: str, status: str) -> Operation:
    return OperationFactory().restore(
        path="backlog/forge-model/20261017-153000/tasks.md",
        stamp="20261017-153000",
        intent="Таблица клиентов",
        mode=mode,
        status=status,
        stop_reason="drop_not_allowed",
        attempts=[(None, None, f"attempt-{n}") for n in (1, 2, 3)],
    )


def test_consent_is_granted_to_stopped_auto_operation_once() -> None:
    operation = _with_mode("auto", "stopped")

    operation.grant_drop()
    operation.grant_drop()

    assert operation.allow_drop is True
    assert operation.status is OperationStatus.STOPPED


def test_consent_is_not_granted_to_running_operation() -> None:
    operation = _with_mode("auto", "running")

    with pytest.raises(OperationNotStoppedError):
        operation.grant_drop()
    assert operation.allow_drop is False


def test_consent_is_not_granted_in_interactive_mode() -> None:
    operation = _with_mode("interactive", "stopped")

    with pytest.raises(OperationDropConsentError):
        operation.grant_drop()
    assert operation.allow_drop is False


@pytest.mark.parametrize("status", ["success", "failure"])
def test_consent_is_not_granted_to_closed_operation(status: str) -> None:
    with pytest.raises(OperationClosedError):
        _with_mode("auto", status).grant_drop()
