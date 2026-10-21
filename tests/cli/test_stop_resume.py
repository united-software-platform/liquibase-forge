"""Команды `forge stop` и `forge resume`: переходы статуса и неизменность беклога."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from forge.cli.main import main
from tests.operation.backlogs import generate, set_values


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    code = main(list(argv))
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    return code, json.loads(lines[0])


def test_stop_by_environment_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = generate(tmp_path)
    before = path.read_text(encoding="utf-8")

    code, payload = _run(capsys, "stop", "--operation", str(path), "--reason", "раннер недоступен")

    assert code == 0
    assert (payload["operation"]["status"], payload["operation"]["stop_reason"]) == (
        "stopped",
        "раннер недоступен",
    )
    tasks_before = before.split("\n---\n", 1)[1]
    assert path.read_text(encoding="utf-8").split("\n---\n", 1)[1] == tasks_before


def test_resume_of_running_operation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = generate(tmp_path)
    before = path.read_bytes()

    code, payload = _run(capsys, "resume", "--operation", str(path))

    assert code == 1
    assert "не остановлена" in payload["refused"]
    assert path.read_bytes() == before


def test_repeated_stop_replaces_reason(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = generate(tmp_path)
    _run(capsys, "stop", "--operation", str(path), "--reason", "первая")

    code, payload = _run(capsys, "stop", "--operation", str(path), "--reason", "вторая")

    assert (code, payload["operation"]["stop_reason"]) == (0, "вторая")


def test_stop_then_resume(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = generate(tmp_path)
    _run(capsys, "stop", "--operation", str(path), "--reason", "отказ владельца")

    code, payload = _run(capsys, "resume", "--operation", str(path))

    assert (code, payload["operation"]["status"], payload["operation"]["stop_reason"]) == (
        0,
        "running",
        None,
    )


@pytest.mark.parametrize("command", [["stop", "--reason", "x"], ["resume"]])
def test_closed_operation_is_not_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], command: list[str]
) -> None:
    path = generate(tmp_path)
    set_values(path, status="success", verdict__attempt_1="success")
    before = path.read_bytes()

    code, payload = _run(capsys, command[0], "--operation", str(path), *command[1:])

    assert code == 1 and "закрыта" in payload["refused"]
    assert path.read_bytes() == before


def test_missing_backlog(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _run(capsys, "resume", "--operation", str(tmp_path / "tasks.md"))

    assert (code, payload["error"]["kind"]) == (2, "operation_unavailable")
