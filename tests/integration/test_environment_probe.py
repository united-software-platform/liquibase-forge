"""Проверка среды на сервере тестов с настоящим Liquibase."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.operation.infrastructure.environment_probe import EnvironmentCheck, EnvironmentProbe
from forge.shared.domain.target_database import TargetDatabase, parse_allowlist
from tests.conftest import TestDatabase
from tests.integration.migration_support import PROJECT_ROOT

PASSED = {"database": True, "allowlist": True, "liquibase": True, "accepted": True}

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("liquibase_ready")]


def _environment(database: TestDatabase, **overrides: str) -> dict[str, str]:
    env = {
        "FORGE_DB_HOST": database.host,
        "FORGE_DB_PORT": str(database.port),
        "FORGE_DB_NAME": database.name,
        "FORGE_DB_USER": database.user,
        "FORGE_DB_PASSWORD": database.password,
        "FORGE_TEST_DB_ALLOWLIST": f"{database.host}:{database.port}/t_*",
    }
    return {**env, **overrides}


def _checks(env: dict[str, str], project: Path = PROJECT_ROOT) -> dict[str, EnvironmentCheck]:
    return {check.name: check for check in EnvironmentProbe(env, project).check()}


def test_all_checks_pass(test_database: TestDatabase) -> None:
    checks = _checks(_environment(test_database))

    assert {name: check.passed for name, check in checks.items()} == PASSED
    assert "Liquibase " in checks["liquibase"].detail


def test_database_outside_allowlist(test_database: TestDatabase) -> None:
    env = _environment(test_database, FORGE_TEST_DB_ALLOWLIST="localhost:5432/lbfr_forge")

    assert {name: check.passed for name, check in _checks(env).items()} == {
        **PASSED,
        "allowlist": False,
    }


def test_prefix_admits_only_test_databases(test_database: TestDatabase) -> None:
    """Шаблон `t_*` пропускает базы тестов и не пускает соседние базы общего экземпляра."""
    env = _environment(test_database)
    allowlist = parse_allowlist(env["FORGE_TEST_DB_ALLOWLIST"])

    assert allowlist.admits(
        TargetDatabase(test_database.host, test_database.port, test_database.name)
    )
    assert not allowlist.admits(TargetDatabase(test_database.host, test_database.port, "shop"))
