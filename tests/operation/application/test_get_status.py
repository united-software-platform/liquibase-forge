"""Сценарий статуса: операция по пути, открытая операция следа, итог проверки среды."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.operation.application.get_status.input import GetStatusInput
from forge.operation.application.get_status.output import GetStatusOutput
from forge.operation.application.get_status.use_case import GetStatusUseCase
from forge.operation.application.operation_reading import (
    OperationUnavailableError,
    SeveralOpenOperationsError,
)
from forge.operation.domain.factory import OperationFactory
from forge.operation.infrastructure.frontmatter import FrontmatterOperationReadRepository
from tests.operation.backlogs import legacy, seed, set_values
from tests.operation.fakes import FakeProbe


def _status(root: Path, path: str | None, probe: FakeProbe | None = None) -> GetStatusOutput:
    use_case = GetStatusUseCase(
        FrontmatterOperationReadRepository(root), probe or FakeProbe(), OperationFactory()
    )
    return use_case.execute(GetStatusInput(path))


def test_operation_after_first_failure(tmp_path: Path) -> None:
    path = legacy(tmp_path)
    set_values(
        path, verdict__attempt_1="failure", backlog__attempt_1="backlog/forge-apply/x-1/tasks.md"
    )

    output = _status(tmp_path, str(path))

    operation = output.operation
    assert operation is not None
    assert (operation.status, operation.used_attempts, operation.confirmed_attempt) == (
        "running",
        1,
        None,
    )
    assert operation.attempts[0].backlog == "backlog/forge-apply/x-1/tasks.md"
    assert output.environment_ok is True


def test_environment_failure_is_reported(tmp_path: Path) -> None:
    output = _status(tmp_path, str(legacy(tmp_path)), FakeProbe(runner=False))

    assert output.environment_ok is False
    assert [(c.name, c.passed) for c in output.checks] == [
        ("database", True),
        ("allowlist", True),
        ("runner", False),
        ("accepted", True),
    ]


def test_latest_without_open_operations(tmp_path: Path) -> None:
    set_values(legacy(tmp_path), status="success")

    output = _status(tmp_path, None)

    assert output.operation is None


def test_latest_finds_stopped_operation(tmp_path: Path) -> None:
    set_values(legacy(tmp_path, "20261017-150000"), status="failure")
    stopped = legacy(tmp_path, "20261017-160000")
    set_values(stopped, status="stopped")

    output = _status(tmp_path, None)

    assert output.operation is not None
    assert (output.operation.path, output.operation.status) == (stopped.as_posix(), "stopped")


def test_latest_finds_open_seed_operation(tmp_path: Path) -> None:
    set_values(legacy(tmp_path, "20261017-150000"), status="success")
    running = seed(tmp_path, "20261017-160000")

    output = _status(tmp_path, None)

    assert output.operation is not None
    assert (output.operation.path, output.operation.status, output.operation.kind) == (
        running.as_posix(),
        "running",
        "seed",
    )


def test_open_operations_of_both_kinds(tmp_path: Path) -> None:
    model = legacy(tmp_path, "20261017-150000")
    filled = seed(tmp_path, "20261017-160000")

    with pytest.raises(SeveralOpenOperationsError) as raised:
        _status(tmp_path, None)

    assert raised.value.paths == (model.as_posix(), filled.as_posix())


def test_legacy_backlog_status_names_model(tmp_path: Path) -> None:
    output = _status(tmp_path, str(legacy(tmp_path)))

    assert output.operation is not None and output.operation.kind == "model"


def test_several_open_operations(tmp_path: Path) -> None:
    legacy(tmp_path, "20261017-150000")
    legacy(tmp_path, "20261017-160000")

    with pytest.raises(SeveralOpenOperationsError):
        _status(tmp_path, None)


def test_missing_backlog(tmp_path: Path) -> None:
    with pytest.raises(OperationUnavailableError):
        _status(tmp_path, str(tmp_path / "tasks.md"))


def test_unknown_status_is_unavailable(tmp_path: Path) -> None:
    path = legacy(tmp_path)
    set_values(path, status="paused")

    with pytest.raises(OperationUnavailableError):
        _status(tmp_path, str(path))
