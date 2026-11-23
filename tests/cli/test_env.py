"""Команды `forge env check` и `forge env up`: JSON-ответы, коды `0` и `2`, разбор глаголов."""

from __future__ import annotations

import argparse
import json
from typing import Any

import pytest

from forge.cli.commands import env
from forge.cli.main import main
from forge.environment.application.check_environment.use_case import CheckEnvironmentOutput
from forge.environment.application.prepare_environment.use_case import PreparationOutput
from forge.shared.application.environment import EnvironmentCheck
from forge.shared.application.settings import (
    DatabaseCredentials,
    DatabaseUnavailableError,
    LiquibaseUnavailableError,
    SettingsUnavailableError,
)

PASSED = (
    EnvironmentCheck("database", True, "подключение выполнено"),
    EnvironmentCheck("allowlist", True, "БД входит в перечень"),
    EnvironmentCheck("liquibase", True, "Liquibase 5.0.4"),
    EnvironmentCheck("accepted", True, "корень принятого состояния db"),
)
PREPARED = PreparationOutput("postgresql-42.7.13.jar", "lbfr_forge", True, True)


def _stdout(capsys: pytest.CaptureFixture[str]) -> tuple[dict[str, Any], str]:
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    return json.loads(lines[0]), captured.err


def _failed(payload: dict[str, Any]) -> list[str]:
    return [check["name"] for check in payload["checks"] if not check["ok"]]


class _Check:
    def __init__(self, *checks: EnvironmentCheck) -> None:
        self.checks = checks

    def execute(self) -> CheckEnvironmentOutput:
        return CheckEnvironmentOutput(self.checks)


class _Prepare:
    def __init__(
        self, output: PreparationOutput | None = None, error: Exception | None = None
    ) -> None:
        self.output = output
        self.error = error

    def execute(self) -> PreparationOutput:
        if self.error is not None:
            raise self.error
        assert self.output is not None
        return self.output


def test_check_prints_every_check(capsys: pytest.CaptureFixture[str]) -> None:
    code = env.run_check(argparse.Namespace(), _Check(*PASSED))

    payload, err = _stdout(capsys)
    assert (code, err) == (0, "")
    assert payload == {
        "checks": [
            {"name": "database", "ok": True, "message": "подключение выполнено"},
            {"name": "allowlist", "ok": True, "message": "БД входит в перечень"},
            {"name": "liquibase", "ok": True, "message": "Liquibase 5.0.4"},
            {"name": "accepted", "ok": True, "message": "корень принятого состояния db"},
        ]
    }


def test_failed_check_keeps_full_report(capsys: pytest.CaptureFixture[str]) -> None:
    checks = (
        EnvironmentCheck("database", False, "connection refused"),
        EnvironmentCheck("allowlist", True, "ок"),
        EnvironmentCheck("liquibase", False, "liquibase не найден в PATH"),
        EnvironmentCheck("accepted", True, "корень db"),
    )

    code = env.run_check(argparse.Namespace(), _Check(*checks))

    payload, err = _stdout(capsys)
    assert code == 2
    assert len(payload["checks"]) == 4
    assert _failed(payload) == ["database", "liquibase"]
    assert "database, liquibase" in err
    assert "error" not in payload


def test_up_reports_preparation(capsys: pytest.CaptureFixture[str]) -> None:
    code = env.run_up(argparse.Namespace(), _Prepare(PREPARED))

    payload, err = _stdout(capsys)
    assert (code, err) == (0, "")
    assert payload == {
        "driver": "postgresql-42.7.13.jar",
        "database": "lbfr_forge",
        "role_created": True,
        "database_created": True,
    }


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (
            SettingsUnavailableError("FORGE_LIQUIBASE_DRIVER_VERSION задана без суммы"),
            "settings_unavailable",
        ),
        (DatabaseUnavailableError("базы нет, нет права CREATEDB"), "database_unavailable"),
        (LiquibaseUnavailableError("не удалось загрузить драйвер"), "liquibase_unavailable"),
    ],
)
def test_up_environment_errors(
    capsys: pytest.CaptureFixture[str], error: Exception, kind: str
) -> None:
    code = env.run_up(argparse.Namespace(), _Prepare(error=error))

    payload, err = _stdout(capsys)
    assert code == 2
    assert payload["error"] == {"kind": kind, "message": str(error)}
    assert str(error) in err


@pytest.mark.parametrize(
    "argv",
    [
        ["env"],
        ["env", "rebuild"],
        ["env", "check", "--extra"],
        ["env", "up", "--extra"],
        ["env", "check", "up"],
    ],
)
def test_usage_errors_are_json_with_code_2(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(argv)

    payload, _ = _stdout(capsys)
    assert code == 2
    assert payload["error"]["kind"] == "usage"


def test_check_without_settings_fails_dependent_checks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Хост и порт имеют умолчания, а имя базы и пароль — нет: среда не настроена, код `2`."""
    for name in ("FORGE_DB_NAME", "FORGE_DB_USER", "FORGE_DB_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    code = main(["env", "check"])

    payload, err = _stdout(capsys)
    assert code == 2
    assert _failed(payload)[:2] == ["database", "allowlist"]
    assert "проверки среды не пройдены" in err


def test_administrator_defaults_to_target_credentials() -> None:
    target = DatabaseCredentials("forge", "secret")

    assert env.administrator({}, target) == target


def test_administrator_overrides_target_credentials() -> None:
    environment = {
        "FORGE_DB_ADMIN_USER": " postgres ",
        "FORGE_DB_ADMIN_PASSWORD": "admin-secret",
    }

    administrator = env.administrator(environment, DatabaseCredentials("forge", "secret"))

    assert administrator == DatabaseCredentials("postgres", "admin-secret")


def test_blank_administrator_means_target_credentials() -> None:
    environment = {"FORGE_DB_ADMIN_USER": "   ", "FORGE_DB_ADMIN_PASSWORD": ""}

    administrator = env.administrator(environment, DatabaseCredentials("forge", "secret"))

    assert administrator == DatabaseCredentials("forge", "secret")
