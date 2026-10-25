"""Команда `forge report`: отчёт об успехе, неудаче и остановке."""

from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from forge.cli.commands import report
from forge.operation.application.build_report.use_case import BuildReportUseCase
from forge.operation.domain.factory import OperationFactory
from forge.operation.infrastructure.accepted_state import FileAcceptedState
from forge.operation.infrastructure.attempt_results import JsonAttemptResultsReader
from forge.operation.infrastructure.frontmatter import FrontmatterOperationReadRepository
from tests.operation.backlogs import ATTEMPT_TRAILS, STAMP, legacy, seed, set_values
from tests.seeding.support import MIGRATION_EXAMPLE

DISCREPANCY = {
    "kind": "column_type_mismatch",
    "table": "customer",
    "column": "email",
    "changeset": None,
    "expected": "string(255)",
    "actual": "text",
    "message": "тип колонки customer.email: ожидался string(255), в БД text",
}


def _report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], path: Path
) -> tuple[int, dict[str, Any]]:
    use_case = BuildReportUseCase(
        FrontmatterOperationReadRepository(tmp_path / "trail"),
        JsonAttemptResultsReader(),
        FileAcceptedState(tmp_path / "db"),
        OperationFactory(),
    )
    code = report.run(argparse.Namespace(operation=str(path)), use_case)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    return code, json.loads(lines[0])


def _failed_attempt(path: Path, number: int) -> None:
    directory = path.parent / f"attempt-{number}"
    directory.mkdir()
    (directory / "reconcile.json").write_text(
        json.dumps({"verdict": "failure", "discrepancies": [DISCREPANCY]}), encoding="utf-8"
    )
    (directory / "rollback.json").write_text(
        json.dumps({"action": "liquibase_rollback", "rolled_back": 1, "verified": True}),
        encoding="utf-8",
    )


def test_success_on_second_attempt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = legacy(tmp_path / "trail")
    _failed_attempt(path, 1)
    set_values(
        path,
        status="success",
        verdict__attempt_1="failure",
        verdict__attempt_2="success",
        backlog__attempt_1=f"backlog/forge-apply/{STAMP}-1/tasks.md",
        backlog__attempt_2=f"backlog/forge-apply/{STAMP}-2/tasks.md",
    )

    code, payload = _report(tmp_path, capsys, path)

    assert code == 0
    assert payload["operation"]["used_attempts"] == 2
    db = (tmp_path / "db").as_posix()
    assert (payload["model"], payload["changelog"]) == (
        f"{db}/model.yaml",
        f"{db}/changelog/{STAMP}.yaml",
    )
    first = payload["attempts"][0]
    assert first["reconcile"]["discrepancies"] == [DISCREPANCY]
    assert (first["rollback"]["action"], first["rollback"]["verified"]) == (
        "liquibase_rollback",
        True,
    )
    assert payload["backlogs"] == [
        str(path),
        f"backlog/forge-apply/{STAMP}-1/tasks.md",
        f"backlog/forge-apply/{STAMP}-2/tasks.md",
    ]
    assert payload["commit"]["files"] == [
        f"{db}/model.yaml",
        f"{db}/changelog/{STAMP}.yaml",
        f"{db}/changelog/master.yaml",
        f"{path.parent.as_posix()}/",
        f"backlog/forge-apply/{STAMP}-1/",
        f"backlog/forge-apply/{STAMP}-2/",
    ]
    assert "след операции" in payload["commit"]["hint"]


def test_failure_after_three_attempts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str, backlog: Callable[..., Path]
) -> None:
    path = backlog(tmp_path / "trail")
    for number in (1, 2, 3):
        _failed_attempt(path, number)
    set_values(
        path,
        status="failure",
        verdict__attempt_1="failure",
        verdict__attempt_2="failure",
        verdict__attempt_3="failure",
    )

    code, payload = _report(tmp_path, capsys, path)

    assert (code, payload["operation"]["kind"]) == (1, kind)
    assert len(payload["attempts"]) == 3
    assert all(
        a["reconcile"]["discrepancies"] and a["rollback"]["verified"] for a in payload["attempts"]
    )
    assert payload["accepted"] is None
    assert payload["commit"]["files"] == [f"{path.parent.as_posix()}/"]
    assert "не изменилось" in payload["commit"]["hint"]
    artifact = {"model": "model", "seed": "seed"}[kind]
    assert payload[artifact].endswith(f"attempt-3/{artifact}.yaml")


def test_stopped_operation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str, backlog: Callable[..., Path]
) -> None:
    path = backlog(tmp_path / "trail")
    set_values(path, status="stopped")
    text = path.read_text(encoding="utf-8").replace(
        "status: stopped\n", 'status: stopped\nstop_reason: "отказ владельца"\n'
    )
    path.write_text(text, encoding="utf-8")

    code, payload = _report(tmp_path, capsys, path)

    assert (code, payload["operation"]["kind"]) == (0, kind)
    assert (payload["operation"]["status"], payload["operation"]["stop_reason"]) == (
        "stopped",
        "отказ владельца",
    )
    assert (payload["attempts"], payload["model"], payload["commit"]) == ([], None, None)


def test_abandoned_operation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str, backlog: Callable[..., Path]
) -> None:
    path = backlog(tmp_path / "trail")
    set_values(
        path,
        status="abandoned",
        verdict__attempt_1="success",
        backlog__attempt_1=f"backlog/{ATTEMPT_TRAILS[kind]}/{STAMP}-1/tasks.md",
    )
    text = path.read_text(encoding="utf-8").replace(
        "status: abandoned\n", 'status: abandoned\nstop_reason: "передумал"\n'
    )
    path.write_text(text, encoding="utf-8")
    directory = path.parent / "attempt-1"
    directory.mkdir()
    (directory / "rollback.json").write_text(
        json.dumps({"action": "liquibase_rollback", "rolled_back": 3, "verified": True}),
        encoding="utf-8",
    )

    code, payload = _report(tmp_path, capsys, path)

    assert code == 0
    assert (payload["operation"]["status"], payload["operation"]["stop_reason"]) == (
        "abandoned",
        "передумал",
    )
    assert payload["attempts"][0]["rollback"]["verified"] is True
    assert payload["accepted"] is None
    assert payload["commit"]["files"] == [
        f"{path.parent.as_posix()}/",
        f"backlog/{ATTEMPT_TRAILS[kind]}/{STAMP}-1/",
    ]
    assert payload["commit"]["hint"] == report.ABANDONED_HINT
    assert payload["operation"]["kind"] == kind


def test_missing_backlog(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _report(tmp_path, capsys, tmp_path / "tasks.md")

    assert (code, payload["error"]["kind"]) == (2, "operation_unavailable")


def test_report_with_accepted_root_outside_db(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = legacy(tmp_path / "trail")
    set_values(path, status="success", verdict__attempt_1="success")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BACKLOG_ROOT", str(tmp_path / "trail"))
    monkeypatch.setenv("FORGE_ACCEPTED_DIR", ".forge/db")

    code = report.run(argparse.Namespace(operation=str(path)))
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["commit"]["files"] == [
        ".forge/db/model.yaml",
        f".forge/db/changelog/{STAMP}.yaml",
        ".forge/db/changelog/master.yaml",
        f"{path.parent.as_posix()}/",
    ]


def test_report_with_invalid_accepted_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = legacy(tmp_path / "trail")
    monkeypatch.setenv("BACKLOG_ROOT", str(tmp_path / "trail"))
    monkeypatch.setenv("FORGE_ACCEPTED_DIR", "../db")

    assert report.run(argparse.Namespace(operation=str(path))) == 2


def test_report_lists_destructive_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    accepted = tmp_path / "db" / "changelog" / f"{STAMP}.yaml"
    accepted.parent.mkdir(parents=True)
    accepted.write_text(
        "databaseChangeLog:\n"
        "- changeSet:\n"
        "    id: 20261017-153000-01\n"
        "    changes:\n"
        "    - dropTable: {tableName: invoice_line}\n"
        "- changeSet:\n"
        "    id: 20261017-153000-02\n"
        "    changes:\n"
        "    - dropColumn: {tableName: customer, columnName: email}\n",
        encoding="utf-8",
    )
    path = legacy(tmp_path / "trail")
    set_values(
        path,
        status="success",
        verdict__attempt_1="success",
        backlog__attempt_1=f"backlog/forge-apply/{STAMP}-1/tasks.md",
    )

    code, payload = _report(tmp_path, capsys, path)

    assert code == 0
    assert payload["operation"]["allow_drop"] is False
    assert payload["destructive"] == [
        {"table": "invoice_line", "column": None},
        {"table": "customer", "column": "email"},
    ]


def test_report_without_drops_has_empty_destructive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, payload = _report(tmp_path, capsys, legacy(tmp_path / "trail"))

    assert payload["destructive"] == []


def test_report_of_successful_seed_operation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stamp = "20261025-101500"
    path = seed(tmp_path / "trail", stamp)
    set_values(
        path,
        status="success",
        verdict__attempt_1="success",
        backlog__attempt_1=f"backlog/forge-seed-apply/{stamp}-1/tasks.md",
    )
    db = tmp_path / "db"
    (db / "changelog").mkdir(parents=True)
    shutil.copyfile(MIGRATION_EXAMPLE / "changelog.yaml", db / "changelog" / f"{stamp}.yaml")

    code, payload = _report(tmp_path, capsys, path)

    root = db.as_posix()
    assert (code, payload["operation"]["kind"]) == (0, "seed")
    assert (payload["model"], payload["seed"], payload["changelog"]) == (
        None,
        f"{root}/seed.yaml",
        f"{root}/changelog/{stamp}.yaml",
    )
    assert payload["rows"] == [
        {"table": "status_group", "inserted": 1, "updated": 0, "deleted": 0},
        {"table": "order_status", "inserted": 2, "updated": 1, "deleted": 1},
    ]
    assert payload["destructive"] == [{"table": "order_status", "key": {"code": "archived"}}]
    assert payload["commit"]["files"] == [
        f"{root}/seed.yaml",
        f"{root}/changelog/{stamp}.yaml",
        f"{root}/changelog/master.yaml",
        f"{path.parent.as_posix()}/",
        f"backlog/forge-seed-apply/{stamp}-1/",
    ]


def test_model_report_has_no_rows(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, payload = _report(tmp_path, capsys, legacy(tmp_path / "trail"))

    assert (payload["operation"]["kind"], payload["rows"], payload["seed"]) == ("model", [], None)
