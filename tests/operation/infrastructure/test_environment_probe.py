"""Проверка среды: каждая проверка независима, сбой называет причину."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from forge.operation.infrastructure.environment_probe import EnvironmentProbe
from forge.shared.application.settings import (
    DatabaseCredentials,
    DatabaseUnavailableError,
    RunnerUnavailableError,
)
from forge.shared.domain.target_database import TargetDatabase
from forge.shared.infrastructure.runner import RunnerSettings

ENV = {
    "FORGE_DB_HOST": "lbfr-db",
    "FORGE_DB_PORT": "5432",
    "FORGE_DB_NAME": "forge",
    "FORGE_DB_USER": "forge",
    "FORGE_DB_PASSWORD": "secret",
    "FORGE_TEST_DB_ALLOWLIST": "lbfr-db:5432/forge",
    "AGENT_RUNNER_URL": "http://runner:11920",
    "AGENT_RUNNER_TOKEN": "token",
}


class _Connection:
    def execute(self, query: str) -> None:
        assert query == "SELECT 1"


class _Connector:
    available = True

    def __init__(self, credentials: DatabaseCredentials) -> None:
        self.credentials = credentials

    @contextmanager
    def connect(self, database: TargetDatabase) -> Iterator[_Connection]:
        if not self.available:
            raise DatabaseUnavailableError(f"БД {database}: connection refused")
        yield _Connection()


class _Down(_Connector):
    available = False


def _runner(calls: list[tuple[str, float]], fail: bool = False) -> Any:
    def call(settings: RunnerSettings, target: str) -> None:
        calls.append((target, settings.timeout))
        if fail:
            raise RunnerUnavailableError("раннер http://runner:11920 недоступен")

    return call


def _checks(
    env: dict[str, str], connector: Any = _Connector, fail: bool = False
) -> dict[str, bool]:
    calls: list[tuple[str, float]] = []
    checks = EnvironmentProbe(env, connector=connector, call=_runner(calls, fail)).check()
    return {c.name: c.passed for c in checks}


def test_all_checks_pass() -> None:
    calls: list[tuple[str, float]] = []

    checks = EnvironmentProbe(ENV, connector=_Connector, call=_runner(calls)).check()  # type: ignore[arg-type]

    assert [(c.name, c.passed) for c in checks] == [
        ("database", True),
        ("allowlist", True),
        ("runner", True),
        ("accepted", True),
    ]
    assert calls == [("help", 30.0)]


def test_database_down() -> None:
    assert _checks(ENV, connector=_Down) == {
        "database": False,
        "allowlist": True,
        "runner": True,
        "accepted": True,
    }


def test_database_outside_allowlist() -> None:
    env = {**ENV, "FORGE_TEST_DB_ALLOWLIST": "lbfr-db-test:5432/*"}

    assert _checks(env) == {
        "database": True,
        "allowlist": False,
        "runner": True,
        "accepted": True,
    }


def test_runner_down() -> None:
    assert _checks(ENV, fail=True) == {
        "database": True,
        "allowlist": True,
        "runner": False,
        "accepted": True,
    }


def test_missing_variables_are_failed_checks() -> None:
    assert _checks({}) == {
        "database": False,
        "allowlist": False,
        "runner": False,
        "accepted": True,
    }


def test_accepted_root_is_named() -> None:
    env = {**ENV, "FORGE_ACCEPTED_DIR": ".forge/db"}
    checks = EnvironmentProbe(env, connector=_Connector, call=_runner([])).check()  # type: ignore[arg-type]

    accepted = {c.name: c for c in checks}["accepted"]
    assert accepted.passed
    assert ".forge/db" in accepted.detail


def test_accepted_root_defaults_to_db() -> None:
    checks = EnvironmentProbe(ENV, connector=_Connector, call=_runner([])).check()  # type: ignore[arg-type]

    assert {c.name: c.detail for c in checks}["accepted"].endswith(" db")


def test_accepted_root_outside_project() -> None:
    env = {**ENV, "FORGE_ACCEPTED_DIR": "../db"}

    assert _checks(env) == {
        "database": True,
        "allowlist": True,
        "runner": True,
        "accepted": False,
    }
