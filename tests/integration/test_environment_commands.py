"""Команды среды на сервере тестов: создание роли и базы, повторный запуск, отказ без прав.

Имена ролей и баз тестов начинаются с `t_env_` и удаляются после теста.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import replace

import psycopg
import pytest
from psycopg import sql

from forge.cli.main import main
from tests.conftest import TestDatabase
from tests.integration.migration_support import PROJECT_ROOT

pytestmark = pytest.mark.integration


def _target(
    monkeypatch: pytest.MonkeyPatch,
    server: TestDatabase,
    database: str,
    role: str,
    password: str,
) -> None:
    """Целевая БД команд — на сервере тестов; администратор не задан."""
    for name, value in {
        "FORGE_DB_HOST": server.host,
        "FORGE_DB_PORT": str(server.port),
        "FORGE_DB_NAME": database,
        "FORGE_DB_USER": role,
        "FORGE_DB_PASSWORD": password,
        "FORGE_DB_ADMIN_USER": "",
        "FORGE_DB_ADMIN_PASSWORD": "",
    }.items():
        monkeypatch.setenv(name, value)


def _exists(server: TestDatabase, query: str, name: str) -> bool:
    with psycopg.connect(replace(server, name="postgres").conninfo) as admin:
        return admin.execute(query, (name,)).fetchone() is not None


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, object]]:
    code = main(list(argv))
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    return code, json.loads(lines[0])


def test_env_up_creates_role_and_database_then_changes_nothing(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    test_database: TestDatabase,
    server_objects: list[tuple[str, str]],
) -> None:
    suffix = uuid.uuid4().hex[:12]
    database, role = f"t_env_{suffix}", f"t_env_r_{suffix}"
    server_objects.append((database, role))
    password = secrets.token_urlsafe(16)
    _target(monkeypatch, test_database, database, role, password)
    monkeypatch.setenv("FORGE_DB_ADMIN_USER", test_database.user)
    monkeypatch.setenv("FORGE_DB_ADMIN_PASSWORD", test_database.password)
    monkeypatch.chdir(PROJECT_ROOT)

    code, payload = _run(capsys, "env", "up")
    again, repeated = _run(capsys, "env", "up")

    assert (code, again) == (0, 0)
    assert (payload["database"], payload["driver"]) == (database, "postgresql-42.7.13.jar")
    assert (payload["role_created"], payload["database_created"]) == (True, True)
    assert (repeated["role_created"], repeated["database_created"]) == (False, False)
    # Роль входит с заданным паролем, база принадлежит ей
    with psycopg.connect(
        host=test_database.host,
        port=test_database.port,
        dbname=database,
        user=role,
        password=password,
    ) as connection:
        owner = connection.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (database,)
        ).fetchone()
    assert owner == (role,)


def test_env_up_second_run_needs_no_administrator(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    test_database: TestDatabase,
    server_objects: list[tuple[str, str]],
) -> None:
    """Роль и база уже есть: forge env up входит учётными данными целевой БД и ничего не меняет."""
    suffix = uuid.uuid4().hex[:12]
    database, role = f"t_env_{suffix}", f"t_env_r_{suffix}"
    server_objects.append((database, role))
    password = secrets.token_urlsafe(16)
    with psycopg.connect(
        replace(test_database, name="postgres").conninfo, autocommit=True
    ) as admin:
        admin.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(database), sql.Identifier(role)
            )
        )
    _target(monkeypatch, test_database, database, role, password)
    monkeypatch.chdir(PROJECT_ROOT)

    code, payload = _run(capsys, "env", "up")

    assert (code, payload["role_created"], payload["database_created"]) == (0, False, False)


def test_env_up_without_administrator_names_the_way_out(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    test_database: TestDatabase,
) -> None:
    """Роли целевой БД нет, администратор не задан: войти нечем, и отказ говорит, что задать."""
    suffix = uuid.uuid4().hex[:12]
    _target(
        monkeypatch,
        test_database,
        f"t_env_{suffix}",
        f"t_env_r_{suffix}",
        secrets.token_urlsafe(16),
    )
    monkeypatch.chdir(PROJECT_ROOT)

    code, payload = _run(capsys, "env", "up")

    error = payload["error"]
    assert code == 2
    assert error["kind"] == "database_unavailable"
    assert "FORGE_DB_ADMIN_USER" in error["message"]
    assert not _exists(
        test_database, "SELECT 1 FROM pg_roles WHERE rolname = %s", f"t_env_r_{suffix}"
    )


def test_env_up_without_rights_changes_nothing(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    test_database: TestDatabase,
    server_objects: list[tuple[str, str]],
) -> None:
    suffix = uuid.uuid4().hex[:12]
    database, role = f"t_env_{suffix}", f"t_env_r_{suffix}"
    limited = f"t_env_a_{suffix}"
    server_objects.append((f"t_env_none_{suffix}", limited))
    limited_password = secrets.token_urlsafe(16)
    with psycopg.connect(
        replace(test_database, name="postgres").conninfo, autocommit=True
    ) as admin:
        # Администратор без права создавать роли и базы
        admin.execute(
            sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}").format(
                sql.Identifier(limited), sql.Literal(limited_password)
            )
        )
    _target(monkeypatch, test_database, database, role, secrets.token_urlsafe(16))
    monkeypatch.setenv("FORGE_DB_ADMIN_USER", limited)
    monkeypatch.setenv("FORGE_DB_ADMIN_PASSWORD", limited_password)
    monkeypatch.chdir(PROJECT_ROOT)

    code, payload = _run(capsys, "env", "up")

    error = payload["error"]
    assert code == 2
    assert error["kind"] == "database_unavailable"
    assert "CREATEROLE" in error["message"]
    assert not _exists(test_database, "SELECT 1 FROM pg_roles WHERE rolname = %s", role)
    assert not _exists(test_database, "SELECT 1 FROM pg_database WHERE datname = %s", database)


def test_env_check_on_shared_server(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    test_database: TestDatabase,
) -> None:
    _target(
        monkeypatch,
        test_database,
        test_database.name,
        test_database.user,
        test_database.password,
    )
    monkeypatch.chdir(PROJECT_ROOT)

    code, payload = _run(capsys, "env", "check")

    assert code == 0
    assert [(check["name"], check["ok"]) for check in payload["checks"]] == [
        ("database", True),
        ("allowlist", True),
        ("liquibase", True),
        ("accepted", True),
    ]
