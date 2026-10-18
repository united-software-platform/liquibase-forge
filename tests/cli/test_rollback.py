"""Команда `forge rollback`: коды `0`, `1`, `2` и отсутствие `rollback.json` при успехе."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from forge.cli.commands import rollback
from forge.cli.main import main
from forge.migration.application.liquibase_gateway import GatewayResult, GatewayUnavailableError
from forge.migration.application.rollback_attempt.use_case import (
    RollbackAttemptUseCase,
    RollbackDependencies,
)
from forge.migration.domain.target_database import TargetDatabase
from forge.migration.infrastructure.json_result_writer import JsonResultWriter
from forge.migration.infrastructure.operation_record_reader import (
    FrontmatterOperationRecordReader,
)
from tests.migration.fakes import FakeDatabase, FakeSettings
from tests.migration.operation_backlog import write_operation


def _rollback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    db: FakeDatabase,
    verdict: str = "failure",
    allowlist: str = "lbfr-db-test:5432/*",
) -> tuple[int, dict[str, Any], Path]:
    operation = write_operation(tmp_path, verdicts=(verdict, "null", "null"))
    use_case = RollbackAttemptUseCase(
        RollbackDependencies(
            operations=FrontmatterOperationRecordReader(),
            settings=FakeSettings(allowlist),
            changelogs=db,
            journal=db,
            schema=db,
            recreator=db,
            gateway=db,
            writer=JsonResultWriter(),
        )
    )
    code = rollback.run(argparse.Namespace(operation=str(operation), attempt=1), use_case)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    return code, json.loads(lines[0]), tmp_path / "attempt-1" / "rollback.json"


def test_success_verdict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = FakeDatabase()
    db.apply_attempt(3)

    code, payload, result = _rollback(tmp_path, capsys, db, verdict="success")

    assert (code, payload["action"], payload["result"]) == (0, "none", None)
    assert not result.exists() and db.calls == []


def test_confirmed_rollback(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = FakeDatabase()
    db.apply_attempt(3)

    code, payload, result = _rollback(tmp_path, capsys, db)

    assert (code, payload["action"], payload["rolled_back"]) == (0, "liquibase_rollback", 3)
    assert json.loads(result.read_text(encoding="utf-8"))["verified"] is True


def test_unconfirmed_return(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = FakeDatabase()
    db.apply_attempt(3)

    def silent(changelog: str, database: TargetDatabase, count: int) -> GatewayResult:
        return GatewayResult("req", 0, "", "")

    db.rollback = silent  # type: ignore[method-assign]

    code, payload, result = _rollback(tmp_path, capsys, db)

    assert (code, payload["verified"]) == (1, False)
    assert json.loads(result.read_text(encoding="utf-8"))["verified"] is False


def test_database_outside_allowlist(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = FakeDatabase()
    db.apply_attempt(3)

    code, payload, result = _rollback(tmp_path, capsys, db, allowlist="lbfr-db:5432/forge")

    assert (code, payload["error"]["kind"]) == (2, "database_not_allowed")
    assert not result.exists()


def test_runner_unavailable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = FakeDatabase()
    db.apply_attempt(3)

    def unavailable(changelog: str, database: TargetDatabase, count: int) -> GatewayResult:
        raise GatewayUnavailableError("runner_unavailable", "раннер недоступен")

    db.rollback = unavailable  # type: ignore[method-assign]

    code, payload, _ = _rollback(tmp_path, capsys, db)

    assert (code, payload["error"]["kind"]) == (2, "runner_unavailable")


def test_attempt_must_be_one_to_three(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["rollback", "--operation", "tasks.md", "--attempt", "4"])

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["kind"] == "usage"


def test_missing_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("FORGE_DB_USER", raising=False)
    operation = write_operation(tmp_path)

    code = main(["rollback", "--operation", str(operation), "--attempt", "1"])

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["kind"] == "settings_unavailable"
