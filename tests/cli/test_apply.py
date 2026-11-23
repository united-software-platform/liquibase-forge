"""Команда `forge apply`: коды `0`, `1`, `2` с подставным шлюзом."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from forge.cli.commands import apply
from forge.cli.main import main
from forge.migration.application.apply_changelog.use_case import ApplyChangelogUseCase
from forge.migration.application.liquibase_gateway import GatewayUnavailableError
from forge.shared.infrastructure.json_result_writer import JsonResultWriter
from tests.migration.fakes import FakeGateway, FakeSettings


def _apply(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    gateway: FakeGateway,
    allowlist: str = "localhost:5432/*",
) -> tuple[int, dict[str, Any], Path]:
    changelog = tmp_path / "attempt-1" / "changelog.yaml"
    use_case = ApplyChangelogUseCase(FakeSettings(allowlist), gateway, JsonResultWriter())
    code = apply.run(argparse.Namespace(changelog=str(changelog)), use_case)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    return code, json.loads(lines[0]), changelog.parent / "apply.json"


def test_successful_apply(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload, result = _apply(tmp_path, capsys, FakeGateway(0))

    assert code == 0
    assert payload["result"] == str(result)
    assert payload["database"] == "localhost:5432/t_0001"
    assert json.loads(result.read_text(encoding="utf-8"))["exit_code"] == 0


def test_liquibase_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload, result = _apply(tmp_path, capsys, FakeGateway(1))

    assert (code, payload["exit_code"]) == (1, 1)
    assert json.loads(result.read_text(encoding="utf-8"))["stderr"] == "ERROR: liquibase"


def test_database_outside_allowlist(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    gateway = FakeGateway(0)

    code, payload, result = _apply(tmp_path, capsys, gateway, allowlist="other-db:5432/forge")

    assert code == 2
    assert payload["error"]["kind"] == "database_not_allowed"
    assert gateway.calls == [] and not result.exists()


def test_liquibase_unavailable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    gateway = FakeGateway(GatewayUnavailableError("liquibase_unavailable", "Liquibase не найден"))

    code, payload, result = _apply(tmp_path, capsys, gateway)

    assert code == 2
    assert payload["error"]["kind"] == "liquibase_unavailable"
    assert not result.exists()


def test_missing_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Хост и порт имеют умолчания, поэтому признак незаданной среды — отсутствие имени базы
    monkeypatch.delenv("FORGE_DB_NAME", raising=False)

    code = main(["apply", "--changelog", "c.yaml"])

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["kind"] == "settings_unavailable"
