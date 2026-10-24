"""Команда `forge abandon`: коды `0`, `1`, `2` и форма ответа.

Беклог операции и `rollback.json` — настоящие файлы, откат идёт настоящим сценарием отката
Миграций поверх подставной БД — так проверяется и сборка адаптера отказа в команде.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from forge.cli.commands import abandon
from forge.cli.main import main
from forge.migration.application.liquibase_gateway import GatewayResult, GatewayUnavailableError
from forge.migration.application.rollback_attempt.use_case import (
    RollbackAttemptUseCase,
    RollbackAttemptUseCaseInterface,
    RollbackDependencies,
)
from forge.migration.infrastructure.operation_record_reader import (
    FrontmatterOperationRecordReader,
)
from forge.shared.application.settings import SettingsUnavailableError
from forge.shared.domain.target_database import TargetDatabase
from forge.shared.infrastructure.json_result_writer import JsonResultWriter
from tests.migration.fakes import FakeDatabase, FakeSettings
from tests.operation.backlogs import STAMP, legacy, set_values

ATTEMPT_BACKLOG = "backlog/forge-apply/{stamp}-{number}/tasks.md"


def _operation(tmp_path: Path, status: str, verdict: str | None = None) -> Path:
    path = legacy(tmp_path / "trail")
    values = {"status": status}
    if verdict is not None:
        values["verdict__attempt_1"] = verdict
        values["backlog__attempt_1"] = ATTEMPT_BACKLOG.format(stamp=STAMP, number=1)
    set_values(path, **values)
    return path


def _rollback(db: FakeDatabase) -> Callable[[], RollbackAttemptUseCaseInterface]:
    def build() -> RollbackAttemptUseCaseInterface:
        return RollbackAttemptUseCase(
            RollbackDependencies(
                operations=FrontmatterOperationRecordReader(),
                settings=FakeSettings("lbfr-db-test:5432/*"),
                changelogs=db,
                journal=db,
                schema=db,
                rows=db,
                recreator=db,
                gateway=db,
                writer=JsonResultWriter(),
            ),
            "db/changelog/master.yaml",
        )

    return build


def _run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    rollback: Callable[[], RollbackAttemptUseCaseInterface],
) -> tuple[int, dict[str, Any]]:
    monkeypatch.setenv("BACKLOG_ROOT", str(tmp_path / "trail"))
    use_case = abandon.build_use_case(rollback)
    code = abandon.run(argparse.Namespace(operation=str(path), reason="передумал"), use_case)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    return code, json.loads(lines[0])


def test_abandon_rolls_back_applied_success_attempt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _operation(tmp_path, "running", "success")
    db = FakeDatabase()
    db.apply_attempt(3)

    code, payload = _run(tmp_path, capsys, monkeypatch, path, _rollback(db))

    assert code == 0
    assert db.calls == ["rollback 3"]
    assert (payload["operation"]["status"], payload["operation"]["stop_reason"]) == (
        "abandoned",
        "передумал",
    )
    assert payload["changed"] is True
    [rollback] = payload["rollbacks"]
    assert (rollback["attempt"], rollback["verified"], rollback["performed"]) == (1, True, True)
    document = json.loads(Path(rollback["result"]).read_text(encoding="utf-8"))
    assert (document["verdict"], document["verified"]) == ("success", True)


def test_abandon_without_attempts_needs_no_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _operation(tmp_path, "stopped")

    def unavailable() -> RollbackAttemptUseCaseInterface:
        raise SettingsUnavailableError("FORGE_DB_HOST не задан")

    code, payload = _run(tmp_path, capsys, monkeypatch, path, unavailable)

    assert code == 0
    assert (payload["operation"]["status"], payload["rollbacks"]) == ("abandoned", [])


def test_repeated_abandon(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _operation(tmp_path, "abandoned")
    before = path.read_text(encoding="utf-8")

    code, payload = _run(tmp_path, capsys, monkeypatch, path, _rollback(FakeDatabase()))

    assert (code, payload["changed"]) == (0, False)
    assert path.read_text(encoding="utf-8") == before


def test_closed_operation_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _operation(tmp_path, "success", "success")
    before = path.read_text(encoding="utf-8")
    db = FakeDatabase()

    code, payload = _run(tmp_path, capsys, monkeypatch, path, _rollback(db))

    assert code == 1
    assert "success" in payload["refused"]
    assert (payload["rollbacks"], db.calls) == ([], [])
    assert path.read_text(encoding="utf-8") == before


def test_unconfirmed_rollback_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _operation(tmp_path, "running", "failure")
    before = path.read_text(encoding="utf-8")
    db = FakeDatabase()
    db.apply_attempt(3)
    # Шлюз отвечает успехом, но записи и объекты попытки остаются: возврат не подтверждён
    db.rollback = lambda changelog, database, count: GatewayResult("req", 0, "", "")  # type: ignore[method-assign]

    code, payload = _run(tmp_path, capsys, monkeypatch, path, _rollback(db))

    assert code == 1
    assert "откат не подтверждён у попыток 1" in payload["refused"]
    assert [(r["attempt"], r["verified"]) for r in payload["rollbacks"]] == [(1, False)]
    assert path.read_text(encoding="utf-8") == before


def test_unavailable_runner_is_environment_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _operation(tmp_path, "running", "success")
    before = path.read_text(encoding="utf-8")
    db = FakeDatabase()
    db.apply_attempt(3)

    def unavailable(changelog: str, target: TargetDatabase, count: int) -> GatewayResult:
        raise GatewayUnavailableError("runner_unavailable", "раннер не отвечает")

    db.rollback = unavailable  # type: ignore[method-assign]

    code, payload = _run(tmp_path, capsys, monkeypatch, path, _rollback(db))

    assert code == 2
    assert payload["error"]["kind"] == "runner_unavailable"
    assert path.read_text(encoding="utf-8") == before


def test_unreadable_backlog_is_environment_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    code = main(["abandon", "--operation", "нет/tasks.md", "--reason", "передумал"])

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["kind"] == "operation_unavailable"


def test_reason_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["abandon", "--operation", "tasks.md"]) == 2
