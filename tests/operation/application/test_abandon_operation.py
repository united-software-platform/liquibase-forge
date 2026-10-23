"""Сценарий отказа от операции: откаты начатых попыток, решение агрегата и запись статуса.

Беклог и `rollback.json` — настоящие файлы во временном следе, откат подменяет заглушка
контракта `AttemptDiscarderInterface`: она пишет `rollback.json`, как сценарий отката Миграций.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge.migration.application.liquibase_gateway import GatewayUnavailableError
from forge.operation.application.abandon_operation.input import AbandonOperationInput
from forge.operation.application.abandon_operation.output import (
    AbandonOperationOutput,
    AbandonRefusedError,
)
from forge.operation.application.abandon_operation.use_case import AbandonOperationUseCase
from forge.operation.domain.factory import OperationFactory
from forge.operation.infrastructure.attempt_results import JsonAttemptResultsReader
from forge.operation.infrastructure.frontmatter import (
    FrontmatterOperationReadRepository,
    FrontmatterOperationWriteRepository,
)
from tests.operation.backlogs import STAMP, legacy, set_values

ATTEMPT_BACKLOG = "backlog/forge-apply/{stamp}-{number}/tasks.md"


class FakeDiscarder:
    """Откат при отказе: исход по номеру попытки, вызовы в журнале, `rollback.json` на диске."""

    def __init__(
        self, verified: dict[int, bool] | None = None, error: Exception | None = None
    ) -> None:
        self.verified = verified or {}
        self.error = error
        self.calls: list[int] = []

    def discard(self, operation_path: str, attempt: int) -> bool:
        self.calls.append(attempt)
        if self.error is not None:
            raise self.error
        verified = self.verified.get(attempt, True)
        _write_rollback(Path(operation_path).parent / f"attempt-{attempt}", verified)
        return verified


def _write_rollback(directory: Path, verified: bool) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "rollback.json").write_text(
        json.dumps({"action": "liquibase_rollback", "rolled_back": 1, "verified": verified}),
        encoding="utf-8",
    )


def _operation(tmp_path: Path, status: str = "running", *verdicts: str, started: int = 0) -> Path:
    path = legacy(tmp_path / "trail")
    values = {"status": status}
    for number in range(1, started + 1):
        values[f"backlog__attempt_{number}"] = ATTEMPT_BACKLOG.format(stamp=STAMP, number=number)
    for number, verdict in enumerate(verdicts, start=1):
        values[f"verdict__attempt_{number}"] = verdict
    set_values(path, **values)
    return path


def _abandon(
    tmp_path: Path, path: Path, discarder: FakeDiscarder, reason: str = "передумал"
) -> AbandonOperationOutput:
    use_case = AbandonOperationUseCase(
        FrontmatterOperationReadRepository(tmp_path / "trail"),
        FrontmatterOperationWriteRepository(),
        JsonAttemptResultsReader(),
        discarder,
        OperationFactory(),
    )
    return use_case.execute(AbandonOperationInput(str(path), reason))


def _status(path: Path) -> str:
    return next(
        line.split(":", 1)[1].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("status:")
    )


def test_abandon_without_started_attempts(tmp_path: Path) -> None:
    path = _operation(tmp_path, "stopped")
    discarder = FakeDiscarder()

    output = _abandon(tmp_path, path, discarder)

    assert discarder.calls == []
    assert (output.operation.status, output.operation.stop_reason) == ("abandoned", "передумал")
    assert (output.rollbacks, output.changed) == ((), True)
    assert _status(path) == "abandoned"


def test_abandon_rolls_back_applied_success_attempt(tmp_path: Path) -> None:
    path = _operation(tmp_path, "running", "success", started=1)
    discarder = FakeDiscarder()

    output = _abandon(tmp_path, path, discarder)

    assert discarder.calls == [1]
    rollback = output.rollbacks[0]
    assert (rollback.attempt, rollback.verified, rollback.performed) == (1, True, True)
    assert rollback.result.endswith("attempt-1/rollback.json")
    assert _status(path) == "abandoned"


def test_attempts_are_discarded_from_last_started(tmp_path: Path) -> None:
    path = _operation(tmp_path, "running", "failure", started=2)
    discarder = FakeDiscarder()

    output = _abandon(tmp_path, path, discarder)

    assert discarder.calls == [2, 1]
    assert [r.attempt for r in output.rollbacks] == [1, 2]


def test_confirmed_rollback_is_not_repeated(tmp_path: Path) -> None:
    path = _operation(tmp_path, "running", "failure", started=2)
    _write_rollback(path.parent / "attempt-1", True)
    discarder = FakeDiscarder()

    output = _abandon(tmp_path, path, discarder)

    assert discarder.calls == [2]
    assert [(r.attempt, r.performed) for r in output.rollbacks] == [(1, False), (2, True)]


def test_unconfirmed_rollback_keeps_status(tmp_path: Path) -> None:
    path = _operation(tmp_path, "running", "failure", started=2)
    before = path.read_text(encoding="utf-8")
    discarder = FakeDiscarder(verified={2: False})

    with pytest.raises(AbandonRefusedError) as error:
        _abandon(tmp_path, path, discarder)

    assert discarder.calls == [2]  # раннюю попытку поверх неснятой поздней не откатывают
    assert "2" in str(error.value)
    assert [(r.attempt, r.verified) for r in error.value.rollbacks] == [(2, False)]
    assert path.read_text(encoding="utf-8") == before


def test_environment_error_keeps_status(tmp_path: Path) -> None:
    path = _operation(tmp_path, "running", "success", started=1)
    before = path.read_text(encoding="utf-8")
    discarder = FakeDiscarder(error=GatewayUnavailableError("runner_unavailable", "нет ответа"))

    with pytest.raises(GatewayUnavailableError):
        _abandon(tmp_path, path, discarder)

    assert path.read_text(encoding="utf-8") == before


def test_repeated_abandon_changes_nothing(tmp_path: Path) -> None:
    path = _operation(tmp_path, "abandoned", "success", started=1)
    before = path.read_text(encoding="utf-8")
    discarder = FakeDiscarder()

    output = _abandon(tmp_path, path, discarder)

    assert (output.changed, discarder.calls) == (False, [])
    assert path.read_text(encoding="utf-8") == before


def test_closed_operation_is_refused_without_rollback(tmp_path: Path) -> None:
    path = _operation(tmp_path, "success", "success", started=1)
    before = path.read_text(encoding="utf-8")
    discarder = FakeDiscarder()

    with pytest.raises(AbandonRefusedError) as error:
        _abandon(tmp_path, path, discarder)

    assert discarder.calls == []
    assert error.value.rollbacks == ()
    assert path.read_text(encoding="utf-8") == before
