"""Общие фикстуры тестов: отдельная БД на каждый интеграционный тест в `lbfr-db-test`."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, replace

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo


@dataclass(frozen=True)
class TestDatabase:
    """БД интеграционного теста на сервере `lbfr-db-test`."""

    __test__ = False  # не тестовый класс, несмотря на префикс имени

    host: str
    port: int
    name: str
    user: str
    password: str

    @property
    def conninfo(self) -> str:
        return make_conninfo(
            host=self.host,
            port=self.port,
            dbname=self.name,
            user=self.user,
            password=self.password,
        )


def _server() -> TestDatabase:
    """Служебная БД сервера `lbfr-db-test`, из которой создаются и удаляются БД тестов."""
    host = os.environ.get("FORGE_TEST_DB_HOST", "")
    if not host:
        pytest.skip("FORGE_TEST_DB_HOST не задан: сервер БД интеграционных тестов не настроен")
    return TestDatabase(
        host=host,
        port=int(os.environ.get("FORGE_TEST_DB_PORT", "5432")),
        name=os.environ.get("FORGE_TEST_DB_NAME", "postgres"),
        user=os.environ.get("FORGE_TEST_DB_USER", ""),
        password=os.environ.get("FORGE_TEST_DB_PASSWORD", ""),
    )


@pytest.fixture
def test_database() -> Iterator[TestDatabase]:
    """Создать БД `t_<uuid>` на время теста и удалить её после.

    Без `FORGE_TEST_DB_HOST` тест пропускается с причиной. Если сервер задан, но недоступен,
    тест падает: недоступная среда не должна выглядеть зелёным прогоном.
    """
    server = _server()
    name = f"t_{uuid.uuid4().hex}"
    with psycopg.connect(server.conninfo, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield replace(server, name=name)
        finally:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
