"""Целевая БД на сервере PostgreSQL: роль и база создаются при отсутствии, существующие не меняются.

Под администратором сервера forge создаёт роль `FORGE_DB_USER` с паролем `FORGE_DB_PASSWORD`
и базу `FORGE_DB_NAME`, владельцем которой служит эта роль. Права проверяются до любого
изменения: при их нехватке на сервере не появляется ничего.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import psycopg
from psycopg import sql

from forge.environment.application.prepare_environment.use_case import Provisioning
from forge.shared.application.settings import (
    DatabaseCredentials,
    DatabaseUnavailableError,
    TargetDatabaseSettingsInterface,
)
from forge.shared.domain.target_database import TargetDatabase
from forge.shared.infrastructure.postgres import PostgresConnector

# Служебная база, через которую создают роли и базы: целевой базы может ещё не быть
MAINTENANCE_DATABASE = "postgres"


def missing_right(
    target: TargetDatabase,
    administrator: str,
    object_: str,
    right: str,
    objects: str,
) -> DatabaseUnavailableError:
    """Отказ до изменения на сервере: объекта нет, а права создавать такие объекты нет."""
    return DatabaseUnavailableError(
        f"{object_} нет на сервере {target.host}:{target.port}, а у администратора "
        f"{administrator} нет права создавать {objects} ({right})"
    )


class PostgresDatabaseProvisioner:
    """Создание роли и базы целевой БД через `psycopg` под администратором сервера."""

    def __init__(
        self,
        settings: TargetDatabaseSettingsInterface,
        administrator: DatabaseCredentials,
        connector: Callable[[DatabaseCredentials], PostgresConnector] = PostgresConnector,
    ) -> None:
        self._settings = settings
        self._administrator = administrator
        self._connector = connector

    def ensure(self) -> Provisioning:
        target = self._settings.target()
        credentials = self._settings.credentials()
        try:
            with self._connect(target) as connection:
                role_exists = self._exists(
                    connection, "SELECT 1 FROM pg_roles WHERE rolname = %s", credentials.user
                )
                database_exists = self._exists(
                    connection, "SELECT 1 FROM pg_database WHERE datname = %s", target.name
                )
                self._require_rights(connection, target, credentials, role_exists, database_exists)
                role_created = False
                if not role_exists:
                    connection.execute(
                        sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                            sql.Identifier(credentials.user), sql.Literal(credentials.password)
                        )
                    )
                    role_created = True
                database_created = False
                if not database_exists:
                    connection.execute(
                        sql.SQL("CREATE DATABASE {} OWNER {}").format(
                            sql.Identifier(target.name), sql.Identifier(credentials.user)
                        )
                    )
                    database_created = True
        except psycopg.Error as error:
            raise DatabaseUnavailableError(
                f"не удалось создать роль или базу на сервере {target.host}:{target.port}: {error}"
            ) from None
        return Provisioning(target.name, role_created, database_created)

    @contextmanager
    def _connect(self, target: TargetDatabase) -> Iterator[psycopg.Connection]:
        """Подключение администратора к служебной базе сервера.

        Администратор не задан — вход идёт учётными данными целевой БД, а пока её роль
        не создана, войти ими нельзя: первый запуск требует администратора сервера.
        """
        try:
            with self._connector(self._administrator).connect(
                target, name=MAINTENANCE_DATABASE
            ) as connection:
                yield connection
        except DatabaseUnavailableError as error:
            if self._administrator.user == self._settings.credentials().user:
                raise DatabaseUnavailableError(
                    f"{error}. Задайте FORGE_DB_ADMIN_USER и FORGE_DB_ADMIN_PASSWORD — "
                    "учётные данные администратора сервера, который создаст роль и базу"
                ) from None
            raise

    def _require_rights(
        self,
        connection: psycopg.Connection,
        target: TargetDatabase,
        credentials: DatabaseCredentials,
        role_exists: bool,
        database_exists: bool,
    ) -> None:
        """Недостающее право — отказ до изменения, а не ответ сервера на попытку."""
        row = connection.execute(
            "SELECT rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        if row is None:
            raise DatabaseUnavailableError(
                f"роль администратора {self._administrator.user} не найдена "
                f"на сервере {target.host}:{target.port}"
            )
        if not role_exists and not row[1]:
            raise missing_right(
                target, self._administrator.user, f"роль {credentials.user}", "CREATEROLE", "роли"
            )
        if not database_exists and not row[0]:
            raise missing_right(
                target, self._administrator.user, f"база {target.name}", "CREATEDB", "базы"
            )

    @staticmethod
    def _exists(connection: psycopg.Connection, query: str, value: str) -> bool:
        return connection.execute(query, (value,)).fetchone() is not None
