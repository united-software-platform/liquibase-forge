"""Фикстуры интеграционных тестов Миграции: раннер, след попытки в проекте, целевая БД."""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.conftest import TestDatabase, environment_missing
from tests.integration.migration_support import PROJECT_ROOT, STAMP
from tests.migration.operation_backlog import write_operation


@pytest.fixture
def runner_configured() -> None:
    if not os.environ.get("AGENT_RUNNER_URL") or not os.environ.get("AGENT_RUNNER_TOKEN"):
        environment_missing("AGENT_RUNNER_URL или AGENT_RUNNER_TOKEN не заданы: раннер не настроен")


@pytest.fixture
def trail(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Каталог следа операции внутри проекта: шлюз принимает changelog только из проекта."""
    monkeypatch.chdir(PROJECT_ROOT)
    directory = Path(".forge") / "test-trails" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    write_operation(directory, subject=STAMP)
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def target(test_database: TestDatabase, monkeypatch: pytest.MonkeyPatch) -> TestDatabase:
    """Целевая БД команд `forge` — БД теста на `lbfr-db-test`."""
    for name, value in {
        "FORGE_DB_HOST": test_database.host,
        "FORGE_DB_PORT": str(test_database.port),
        "FORGE_DB_NAME": test_database.name,
        "FORGE_DB_USER": test_database.user,
        "FORGE_DB_PASSWORD": test_database.password,
    }.items():
        monkeypatch.setenv(name, value)
    return test_database
