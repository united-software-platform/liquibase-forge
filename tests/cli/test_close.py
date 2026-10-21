"""Команда `forge close`: принятие в `db/`, `failure` без `db/`, раннее и повторное закрытие."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from forge.cli.commands import close
from forge.operation.application.close_operation.use_case import CloseOperationUseCase
from forge.operation.domain.factory import OperationFactory
from forge.operation.infrastructure.accepted_state import FileAcceptedState
from forge.operation.infrastructure.attempt_results import JsonAttemptResultsReader
from forge.operation.infrastructure.frontmatter import (
    FrontmatterOperationReadRepository,
    FrontmatterOperationWriteRepository,
)
from tests.operation.backlogs import STAMP, legacy, set_values


def _close(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], path: Path
) -> tuple[int, dict[str, Any]]:
    use_case = CloseOperationUseCase(
        FrontmatterOperationReadRepository(tmp_path / "trail"),
        FrontmatterOperationWriteRepository(),
        JsonAttemptResultsReader(),
        FileAcceptedState(tmp_path / "db"),
        OperationFactory(),
    )
    code = close.run(argparse.Namespace(operation=str(path)), use_case)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    return code, json.loads(lines[0])


def _attempt(path: Path, number: int, rollback_verified: bool | None = None) -> None:
    directory = path.parent / f"attempt-{number}"
    directory.mkdir()
    (directory / "model.yaml").write_text(f"# модель попытки {number}\n", encoding="utf-8")
    (directory / "changelog.yaml").write_text(f"# changelog попытки {number}\n", encoding="utf-8")
    if rollback_verified is not None:
        (directory / "rollback.json").write_text(
            json.dumps(
                {"action": "liquibase_rollback", "rolled_back": 1, "verified": rollback_verified}
            ),
            encoding="utf-8",
        )


def test_first_successful_operation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = legacy(tmp_path / "trail")
    _attempt(path, 1, rollback_verified=True)
    _attempt(path, 2)
    set_values(path, verdict__attempt_1="failure", verdict__attempt_2="success")

    code, payload = _close(tmp_path, capsys, path)

    assert code == 0
    assert (payload["operation"]["status"], payload["accepted_attempt"], payload["changed"]) == (
        "success",
        2,
        True,
    )
    db = tmp_path / "db"
    assert (db / "model.yaml").read_text(encoding="utf-8") == "# модель попытки 2\n"
    assert (db / "changelog" / f"{STAMP}.yaml").read_text(
        encoding="utf-8"
    ) == "# changelog попытки 2\n"
    assert f"file: {STAMP}.yaml" in (db / "changelog" / "master.yaml").read_text(encoding="utf-8")
    assert "status: success" in path.read_text(encoding="utf-8")


def test_three_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = legacy(tmp_path / "trail")
    for number in (1, 2, 3):
        _attempt(path, number, rollback_verified=True)
    set_values(
        path,
        verdict__attempt_1="failure",
        verdict__attempt_2="failure",
        verdict__attempt_3="failure",
    )

    code, payload = _close(tmp_path, capsys, path)

    assert (code, payload["operation"]["status"], payload["accepted"]) == (0, "failure", None)
    assert not (tmp_path / "db").exists()


def test_three_failures_with_unconfirmed_rollback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = legacy(tmp_path / "trail")
    for number, verified in ((1, True), (2, True), (3, False)):
        _attempt(path, number, rollback_verified=verified)
    set_values(
        path,
        verdict__attempt_1="failure",
        verdict__attempt_2="failure",
        verdict__attempt_3="failure",
    )

    code, payload = _close(tmp_path, capsys, path)

    assert code == 1 and "попыток 3" in payload["refused"]
    assert "status: running" in path.read_text(encoding="utf-8")


def test_premature_close(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = legacy(tmp_path / "trail")
    _attempt(path, 1, rollback_verified=True)
    set_values(path, verdict__attempt_1="failure")
    before = path.read_bytes()

    code, payload = _close(tmp_path, capsys, path)

    assert code == 1 and "закрывать рано" in payload["refused"]
    assert path.read_bytes() == before
    assert not (tmp_path / "db").exists()


def test_repeated_close(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = legacy(tmp_path / "trail")
    _attempt(path, 1)
    set_values(path, verdict__attempt_1="success")
    _close(tmp_path, capsys, path)
    backlog = path.read_bytes()
    master = (tmp_path / "db" / "changelog" / "master.yaml").read_bytes()

    code, payload = _close(tmp_path, capsys, path)

    assert (code, payload["changed"], payload["operation"]["status"]) == (0, False, "success")
    assert payload["accepted"]["model"].endswith("db/model.yaml")
    assert path.read_bytes() == backlog
    assert (tmp_path / "db" / "changelog" / "master.yaml").read_bytes() == master


def test_acceptance_failure_keeps_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = legacy(tmp_path / "trail")
    set_values(path, verdict__attempt_1="success")

    code, payload = _close(tmp_path, capsys, path)

    assert (code, payload["error"]["kind"]) == (2, "acceptance_failed")
    assert "status: running" in path.read_text(encoding="utf-8")


def _close_from_environment(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    accepted_dir: str | None,
) -> tuple[int, dict[str, Any]]:
    """Закрыть успешную операцию сценарием, собранным командой из окружения процесса."""
    path = legacy(tmp_path / "trail")
    _attempt(path, 1)
    set_values(path, verdict__attempt_1="success")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BACKLOG_ROOT", str(tmp_path / "trail"))
    if accepted_dir is None:
        monkeypatch.delenv("FORGE_ACCEPTED_DIR", raising=False)
    else:
        monkeypatch.setenv("FORGE_ACCEPTED_DIR", accepted_dir)
    code = close.run(argparse.Namespace(operation=str(path)))
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return code, json.loads(lines[0])


def test_accepted_root_defaults_to_db(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, payload = _close_from_environment(tmp_path, capsys, monkeypatch, None)

    assert code == 0
    assert payload["accepted"]["model"] == "db/model.yaml"
    assert (tmp_path / "db" / "model.yaml").is_file()


def test_accepted_root_outside_db(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, payload = _close_from_environment(tmp_path, capsys, monkeypatch, ".forge/db")

    assert code == 0
    assert payload["accepted"]["model"] == ".forge/db/model.yaml"
    assert (tmp_path / ".forge" / "db" / "model.yaml").is_file()
    assert not (tmp_path / "db").exists()


def test_absolute_accepted_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, payload = _close_from_environment(tmp_path, capsys, monkeypatch, "/srv/db")

    assert code == 2
    assert "FORGE_ACCEPTED_DIR" in json.dumps(payload, ensure_ascii=False)
    assert not (tmp_path / "db").exists()
    backlog = tmp_path / "trail" / "forge-model" / STAMP / "tasks.md"
    assert "status: running" in backlog.read_text(encoding="utf-8")
