"""Проверка среды: каждая проверка независима, сбой называет причину."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from forge.operation.infrastructure.environment_probe import EnvironmentProbe
from forge.shared.application.settings import (
    DatabaseCredentials,
    DatabaseUnavailableError,
)
from forge.shared.domain.target_database import TargetDatabase
from forge.shared.infrastructure.liquibase import Process, driver_path

ENV = {
    "FORGE_DB_HOST": "localhost",
    "FORGE_DB_PORT": "5432",
    "FORGE_DB_NAME": "forge",
    "FORGE_DB_USER": "forge",
    "FORGE_DB_PASSWORD": "secret",
    "FORGE_TEST_DB_ALLOWLIST": "localhost:5432/forge",
}
VERSION = subprocess.CompletedProcess[str](
    ["liquibase", "--version"], 0, "\nLiquibase Version: 5.0.4\n", ""
)
PASSED = {"database": True, "allowlist": True, "liquibase": True, "accepted": True}


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


def _liquibase(outcome: Process | Exception = VERSION) -> Callable[[list[str]], Process]:
    def run(command: list[str]) -> Process:
        assert command == ["liquibase", "--version"]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return run


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Корень проекта с драйвером в `.forge/lib/`."""
    driver = driver_path(tmp_path, {})
    driver.parent.mkdir(parents=True)
    driver.write_bytes(b"jar")
    return tmp_path


def _probe(env: dict[str, str], project: Path, connector: Any = _Connector, outcome=VERSION):
    run = _liquibase(outcome)
    return EnvironmentProbe(env, project, connector=connector, run=run).check()  # type: ignore[arg-type]


def _passed(env: dict[str, str], project: Path, connector: Any = _Connector) -> dict[str, bool]:
    return {check.name: check.passed for check in _probe(env, project, connector)}


def _one_failed(name: str) -> dict[str, bool]:
    return {**PASSED, name: False}


def test_all_checks_pass(project: Path) -> None:
    checks = _probe(ENV, project)

    assert [(check.name, check.passed) for check in checks] == [
        ("database", True),
        ("allowlist", True),
        ("liquibase", True),
        ("accepted", True),
    ]
    detail = {check.name: check.detail for check in checks}["liquibase"]
    assert "5.0.4" in detail
    assert "postgresql-42.7.13.jar" in detail


def test_database_down(project: Path) -> None:
    assert _passed(ENV, project, connector=_Down) == _one_failed("database")


def test_database_outside_allowlist(project: Path) -> None:
    env = {**ENV, "FORGE_TEST_DB_ALLOWLIST": "other-db:5432/*"}

    assert _passed(env, project) == _one_failed("allowlist")


def test_liquibase_missing_executable(project: Path) -> None:
    checks = _probe(ENV, project, outcome=FileNotFoundError("liquibase"))

    assert {check.name: check.passed for check in checks} == _one_failed("liquibase")
    detail = {check.name: check.detail for check in checks}["liquibase"]
    assert "mise install" in detail


def test_driver_missing(project: Path) -> None:
    driver_path(project, {}).unlink()

    checks = _probe(ENV, project)

    assert {check.name: check.passed for check in checks} == _one_failed("liquibase")
    detail = {check.name: check.detail for check in checks}["liquibase"]
    assert "forge env up" in detail


def test_liquibase_hanging(project: Path) -> None:
    checks = _probe(ENV, project, outcome=subprocess.TimeoutExpired(["liquibase"], 30))

    assert {check.name: check.passed for check in checks} == _one_failed("liquibase")


def test_missing_variables_are_failed_checks(project: Path) -> None:
    assert _passed({}, project) == {**PASSED, "database": False, "allowlist": False}


def test_accepted_root_is_named(project: Path) -> None:
    checks = _probe({**ENV, "FORGE_ACCEPTED_DIR": ".forge/db"}, project)

    accepted = {check.name: check for check in checks}["accepted"]
    assert accepted.passed
    assert ".forge/db" in accepted.detail


def test_accepted_root_defaults_to_db(project: Path) -> None:
    checks = _probe(ENV, project)

    assert {check.name: check.detail for check in checks}["accepted"].endswith(" db")


def test_accepted_root_outside_project(project: Path) -> None:
    assert _passed({**ENV, "FORGE_ACCEPTED_DIR": "../db"}, project) == _one_failed("accepted")
