"""Проверка среды на `lbfr-db-test` и настоящем раннере."""

from __future__ import annotations

import os

import pytest

from forge.operation.infrastructure.environment_probe import EnvironmentProbe
from tests.conftest import TestDatabase

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("runner_configured")]


def _environment(database: TestDatabase, **overrides: str) -> dict[str, str]:
    env = {
        "FORGE_DB_HOST": database.host,
        "FORGE_DB_PORT": str(database.port),
        "FORGE_DB_NAME": database.name,
        "FORGE_DB_USER": database.user,
        "FORGE_DB_PASSWORD": database.password,
        "FORGE_TEST_DB_ALLOWLIST": f"{database.host}:{database.port}/*",
        "AGENT_RUNNER_URL": os.environ["AGENT_RUNNER_URL"],
        "AGENT_RUNNER_TOKEN": os.environ["AGENT_RUNNER_TOKEN"],
    }
    return {**env, **overrides}


def _passed(env: dict[str, str]) -> dict[str, bool]:
    return {check.name: check.passed for check in EnvironmentProbe(env).check()}


def test_all_checks_pass(test_database: TestDatabase) -> None:
    assert _passed(_environment(test_database)) == {
        "database": True,
        "allowlist": True,
        "runner": True,
    }


def test_database_outside_allowlist(test_database: TestDatabase) -> None:
    env = _environment(test_database, FORGE_TEST_DB_ALLOWLIST="lbfr-db:5432/forge")

    assert _passed(env) == {"database": True, "allowlist": False, "runner": True}


def test_wrong_runner_token(test_database: TestDatabase) -> None:
    env = _environment(test_database, AGENT_RUNNER_TOKEN="wrong-token")

    assert _passed(env) == {"database": True, "allowlist": True, "runner": False}
