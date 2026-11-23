"""Фикстуры интеграционных тестов Миграции: Liquibase, след попытки в проекте, целевая БД."""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from forge.shared.infrastructure.liquibase import driver_path
from tests.conftest import TestDatabase, environment_missing
from tests.integration.migration_support import PROJECT_ROOT, STAMP
from tests.migration.operation_backlog import write_operation


@pytest.fixture
def liquibase_ready() -> None:
    """Пропустить тест без нативного Liquibase: без файла в `PATH` или драйвера в `.forge/lib/`.

    Драйвер в локальный каталог кладёт `forge env up`. При `FORGE_REQUIRE_INTEGRATION=1`
    отсутствие окружения — ошибка, а не пропуск.
    """
    if shutil.which("liquibase") is None:
        environment_missing(
            "liquibase не найден в PATH: установите инструменты командой mise install"
        )
    if not driver_path(PROJECT_ROOT, os.environ).is_file():
        environment_missing("драйвер PostgreSQL не найден в .forge/lib: выполните forge env up")


@pytest.fixture
def server_objects(test_database: TestDatabase) -> Iterator[list[tuple[str, str]]]:
    """Реестр созданных тестом пар «база — роль»; удаляются после теста под администратором.

    Сервер тестов — общий экземпляр workspace: чужие объекты на нём оставаться не должны.
    """
    pairs: list[tuple[str, str]] = []
    yield pairs
    with psycopg.connect(
        replace(test_database, name="postgres").conninfo, autocommit=True
    ) as admin:
        for database, role in reversed(pairs):
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
            )
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


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
    """Целевая БД команд `forge` — БД теста на сервере тестов."""
    for name, value in {
        "FORGE_DB_HOST": test_database.host,
        "FORGE_DB_PORT": str(test_database.port),
        "FORGE_DB_NAME": test_database.name,
        "FORGE_DB_USER": test_database.user,
        "FORGE_DB_PASSWORD": test_database.password,
    }.items():
        monkeypatch.setenv(name, value)
    return test_database
