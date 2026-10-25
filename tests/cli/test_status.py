"""Команда `forge status`: операция, ключ `--latest` и код по проверке среды."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from forge.cli.commands import status
from forge.cli.main import main
from forge.operation.application.get_status.use_case import GetStatusUseCase
from forge.operation.domain.factory import OperationFactory
from forge.operation.infrastructure.frontmatter import FrontmatterOperationReadRepository
from tests.operation.backlogs import generate, legacy, seed, set_values
from tests.operation.fakes import FakeProbe


def _status(
    root: Path,
    capsys: pytest.CaptureFixture[str],
    operation: str | None,
    probe: FakeProbe | None = None,
) -> tuple[int, dict[str, Any]]:
    use_case = GetStatusUseCase(
        FrontmatterOperationReadRepository(root), probe or FakeProbe(), OperationFactory()
    )
    code = status.run(argparse.Namespace(operation=operation, latest=operation is None), use_case)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    return code, json.loads(lines[0])


def test_status_names_mode_and_consent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _status(tmp_path, capsys, str(generate(tmp_path, allow_drop=True)))

    assert code == 0
    assert (payload["operation"]["mode"], payload["operation"]["allow_drop"]) == ("auto", True)


def test_legacy_backlog_status_gives_consent_false(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = _status(tmp_path, capsys, str(legacy(tmp_path)))

    assert code == 0
    assert payload["operation"]["allow_drop"] is False


def test_operation_after_first_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = generate(tmp_path)
    set_values(path, verdict__attempt_1="failure")

    code, payload = _status(tmp_path, capsys, str(path))

    assert code == 0
    operation = payload["operation"]
    assert (operation["status"], operation["used_attempts"], operation["confirmed_attempt"]) == (
        "running",
        1,
        None,
    )
    assert operation["intent"] == "Справочник клиентов: id, email, имя"
    assert [a["verdict"] for a in operation["attempts"]] == ["failure", None, None]


def test_runner_down(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _status(tmp_path, capsys, str(generate(tmp_path)), FakeProbe(runner=False))

    assert code == 2
    assert payload["environment_ok"] is False
    assert [(c["check"], c["passed"]) for c in payload["environment"]] == [
        ("database", True),
        ("allowlist", True),
        ("runner", False),
        ("accepted", True),
    ]


def test_accepted_root_outside_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _status(tmp_path, capsys, str(generate(tmp_path)), FakeProbe(accepted=False))

    assert code == 2
    assert payload["environment_ok"] is False
    assert {c["check"]: c["passed"] for c in payload["environment"]}["accepted"] is False


def test_latest_without_open_operations(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _status(tmp_path / "missing-trail", capsys, None)

    assert (code, payload["operation"]) == (0, None)


def test_latest_finds_stopped(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    stopped = legacy(tmp_path)
    set_values(stopped, status="stopped")

    code, payload = _status(tmp_path, capsys, None)

    assert (code, payload["operation"]["path"], payload["operation"]["status"]) == (
        0,
        stopped.as_posix(),
        "stopped",
    )


def test_status_names_kind(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str, backlog: Callable[..., Path]
) -> None:
    code, payload = _status(tmp_path, capsys, str(backlog(tmp_path)))

    assert (code, payload["operation"]["kind"]) == (0, kind)


def test_latest_finds_open_seed_operation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    set_values(legacy(tmp_path, "20261017-150000"), status="success")
    running = seed(tmp_path, "20261017-160000")

    code, payload = _status(tmp_path, capsys, None)

    operation = payload["operation"]
    assert (code, operation["path"], operation["status"], operation["kind"]) == (
        0,
        running.as_posix(),
        "running",
        "seed",
    )


def test_open_operations_of_both_kinds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    model = legacy(tmp_path, "20261017-150000")
    filled = seed(tmp_path, "20261017-160000")

    code, payload = _status(tmp_path, capsys, None)

    assert (code, payload["error"]["kind"]) == (2, "several_open_operations")
    assert payload["error"]["operations"] == [model.as_posix(), filled.as_posix()]


def test_several_open_operations(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    legacy(tmp_path, "20261017-150000")
    legacy(tmp_path, "20261017-160000")

    code, payload = _status(tmp_path, capsys, None)

    assert (code, payload["error"]["kind"]) == (2, "several_open_operations")
    assert len(payload["error"]["operations"]) == 2


def test_missing_backlog(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _status(tmp_path, capsys, str(tmp_path / "tasks.md"))

    assert (code, payload["error"]["kind"]) == (2, "operation_unavailable")


def test_operation_or_latest_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["status"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["kind"] == "usage"
