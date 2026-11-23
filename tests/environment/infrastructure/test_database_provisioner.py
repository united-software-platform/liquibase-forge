"""Подготовка целевой БД: роль и база создаются при отсутствии, права проверяются до изменения."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
import pytest
from psycopg import sql

from forge.environment.application.prepare_environment.use_case import Provisioning
from forge.environment.infrastructure.database_provisioner import PostgresDatabaseProvisioner
from forge.shared.application.settings import (
    DatabaseCredentials,
    DatabaseUnavailableError,
    SettingsUnavailableError,
)
from forge.shared.domain.target_database import TargetDatabase

TARGET = TargetDatabase("localhost", 5432, "forge_db")
USER = DatabaseCredentials("forge_user", "secret")


class _Settings:
    """Настройки цели: без пользователя — ошибка настроек, как у незаданных переменных."""

    def __init__(self, user: DatabaseCredentials | None = USER) -> None:
        self._user = user

    def target(self) -> TargetDatabase:
        return TARGET

    def credentials(self) -> DatabaseCredentials:
        if self._user is None:
            raise SettingsUnavailableError("переменная окружения FORGE_DB_USER не задана")
        return self._user


class _Result:
    def __init__(self, row: tuple | None) -> None:
        self._row = row

    def fetchone(self) -> tuple | None:
        return self._row


class _Connection:
    """Подставное подключение к служебной базе: состояния сервера и ответ на каждый оператор."""

    def __init__(
        self,
        *,
        role: bool = False,
        database: bool = False,
        createrole: bool = True,
        createdb: bool = True,
        deny_database: bool = False,
    ) -> None:
        self.role = role
        self.database = database
        self.createrole = createrole
        self.createdb = createdb
        self.deny_database = deny_database
        self.statements: list[str] = []

    def execute(self, query: str | sql.Composable, params: tuple | None = None) -> _Result:
        text = query.as_string(None) if isinstance(query, sql.Composable) else query
        self.statements.append(text)
        if text.startswith("SELECT 1 FROM pg_roles"):
            return _Result((1,) if self.role else None)
        if text.startswith("SELECT 1 FROM pg_database"):
            return _Result((1,) if self.database else None)
        if text.startswith("SELECT rolcreatedb"):
            return _Result((self.createdb, self.createrole))
        if text.startswith("CREATE DATABASE") and self.deny_database:
            raise psycopg.errors.InsufficientPrivilege("permission denied to create database")
        return _Result(None)

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _Connector:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.log: list[tuple[str, str | None, str]] = []

    @contextmanager
    def connect(self, database: TargetDatabase, name: str | None = None) -> Iterator[_Connection]:
        self.log.append((f"{database.host}:{database.port}", name, "administrator"))
        yield self.connection


def _provisioner(
    connection: _Connection,
    administrator: DatabaseCredentials | None = None,
    user: DatabaseCredentials | None = USER,
) -> tuple[PostgresDatabaseProvisioner, _Connector]:
    connector = _Connector(connection)

    def factory(credentials: DatabaseCredentials) -> _Connector:
        return connector

    provisioner = PostgresDatabaseProvisioner(
        _Settings(user), administrator or DatabaseCredentials("admin", "admin"), factory
    )
    return provisioner, connector


def _creates(connection: _Connection) -> list[str]:
    return [statement for statement in connection.statements if "CREATE" in statement]


def test_first_run_creates_role_and_database() -> None:
    connection = _Connection()
    provisioner, connector = _provisioner(connection)

    provisioning = provisioner.ensure()

    assert provisioning == Provisioning("forge_db", True, True)
    assert _creates(connection) == [
        "CREATE ROLE \"forge_user\" LOGIN PASSWORD 'secret'",
        'CREATE DATABASE "forge_db" OWNER "forge_user"',
    ]
    assert connector.log == [("localhost:5432", "postgres", "administrator")]


def test_existing_role_and_database_are_unchanged() -> None:
    connection = _Connection(role=True, database=True)
    provisioner, _ = _provisioner(connection)

    assert provisioner.ensure() == Provisioning("forge_db", False, False)
    assert _creates(connection) == []


def test_existing_role_needs_only_database() -> None:
    connection = _Connection(role=True)
    provisioner, _ = _provisioner(connection)

    assert provisioner.ensure() == Provisioning("forge_db", False, True)
    assert _creates(connection) == ['CREATE DATABASE "forge_db" OWNER "forge_user"']


def test_missing_role_without_createrole_changes_nothing() -> None:
    connection = _Connection(createrole=False)
    provisioner, _ = _provisioner(connection)

    with pytest.raises(DatabaseUnavailableError, match=r"роль forge_user.*CREATEROLE"):
        provisioner.ensure()

    assert _creates(connection) == []


def test_missing_database_without_createdb_changes_nothing() -> None:
    connection = _Connection(role=True, createdb=False)
    provisioner, _ = _provisioner(connection)

    with pytest.raises(DatabaseUnavailableError, match=r"база forge_db.*CREATEDB"):
        provisioner.ensure()

    assert _creates(connection) == []


def test_missing_role_is_reported_before_missing_database() -> None:
    """Оба права отсутствуют: первым называется роль — иначе база осталась бы без владельца."""
    connection = _Connection(createrole=False, createdb=False)
    provisioner, _ = _provisioner(connection)

    with pytest.raises(DatabaseUnavailableError, match="CREATEROLE"):
        provisioner.ensure()

    assert _creates(connection) == []


def test_server_refusal_is_environment_error() -> None:
    connection = _Connection(role=True, deny_database=True)
    provisioner, _ = _provisioner(connection)

    with pytest.raises(DatabaseUnavailableError, match=r"localhost:5432.*permission denied"):
        provisioner.ensure()


def test_unreachable_server_keeps_environment_error() -> None:
    def refuse(credentials: DatabaseCredentials) -> _Connector:
        raise DatabaseUnavailableError("сервер недоступен")

    provisioner = PostgresDatabaseProvisioner(_Settings(), USER, refuse)

    with pytest.raises(DatabaseUnavailableError, match="сервер недоступен"):
        provisioner.ensure()


def test_special_characters_are_quoted() -> None:
    connection = _Connection()
    user = DatabaseCredentials('weird"user', "sec'ret")
    provisioner, _ = _provisioner(connection, user=user)

    provisioner.ensure()

    expected = "CREATE ROLE \"weird\"\"user\" LOGIN PASSWORD 'sec''ret'"
    assert _creates(connection)[0] == expected


def test_unconfigured_settings_are_not_hidden() -> None:
    """Незаданные переменные — ошибка настроек, а не сбой сервера."""
    connection = _Connection()
    provisioner, connector = _provisioner(connection, user=None)

    with pytest.raises(SettingsUnavailableError, match="FORGE_DB_USER"):
        provisioner.ensure()

    assert connector.log == []
    assert connection.statements == []
