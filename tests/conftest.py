"""Общие фикстуры тестов: отдельная БД на каждый интеграционный тест на сервере тестов."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import NoReturn

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from forge.shared.infrastructure.settings import DEFAULT_HOST, server_port


@dataclass(frozen=True)
class TestDatabase:
    """БД интеграционного теста на сервере тестов — общем экземпляре PostgreSQL workspace."""

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


def environment_missing(reason: str) -> NoReturn:
    """Пропустить тест без окружения, а при `FORGE_REQUIRE_INTEGRATION=1` — завершить его ошибкой.

    Признак задаёт workflow проверок: в CI окружение поднято, и пропуск означал бы, что оно
    не дошло до тестов, — такой прогон не должен выглядеть зелёным. Локально без признака
    поведение прежнее: пропуск с причиной.
    """
    if os.environ.get("FORGE_REQUIRE_INTEGRATION") == "1":
        pytest.fail(f"{reason} (FORGE_REQUIRE_INTEGRATION=1: пропуск запрещён)")
    pytest.skip(reason)


def _server() -> TestDatabase:
    """Служебная БД сервера тестов, из которой создаются и удаляются БД тестов.

    Адрес — как у целевой БД: хост по умолчанию `localhost`, порт — `PG_PORT` каскада mise,
    иначе `5432`. Признак настроенного сервера — учётные данные: роль должна уметь создавать базы.
    """
    user = os.environ.get("FORGE_TEST_DB_USER", "")
    password = os.environ.get("FORGE_TEST_DB_PASSWORD", "")
    if not user or not password:
        environment_missing(
            "FORGE_TEST_DB_USER или FORGE_TEST_DB_PASSWORD не заданы: "
            "сервер БД интеграционных тестов не настроен"
        )
    return TestDatabase(
        host=os.environ.get("FORGE_TEST_DB_HOST", "").strip() or DEFAULT_HOST,
        port=int(os.environ.get("FORGE_TEST_DB_PORT", "").strip() or server_port(os.environ)),
        name=os.environ.get("FORGE_TEST_DB_NAME", "postgres"),
        user=user,
        password=password,
    )


@pytest.fixture
def test_database() -> Iterator[TestDatabase]:
    """Создать БД `t_<uuid>` на время теста и удалить её после.

    Без `FORGE_TEST_DB_HOST` тест пропускается с причиной (при `FORGE_REQUIRE_INTEGRATION=1` —
    падает). Если сервер задан, но недоступен,
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
