"""Проверка тестовой среды.

Целевая БД, перечень тестовых БД, Liquibase с драйвером и корень принятого состояния.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from forge.shared.application.environment import EnvironmentCheck
from forge.shared.application.settings import (
    DatabaseCredentials,
    DatabaseUnavailableError,
    LiquibaseUnavailableError,
    SettingsUnavailableError,
)
from forge.shared.domain.target_database import DatabaseNotAllowedError
from forge.shared.infrastructure.liquibase import (
    Runner,
    driver_path,
    require_liquibase,
    run_liquibase,
)
from forge.shared.infrastructure.postgres import PostgresConnector
from forge.shared.infrastructure.settings import EnvironmentSettings


class EnvironmentProbe:
    """Реализация проверки среды по переменным окружения процесса.

    Драйвер Liquibase ищется в `.forge/lib/` каталога `project_root` — корня проекта, из которого
    запущен CLI.
    """

    def __init__(
        self,
        environment: Mapping[str, str],
        project_root: Path,
        connector: Callable[[DatabaseCredentials], PostgresConnector] = PostgresConnector,
        run: Runner = run_liquibase,
    ) -> None:
        self._env = environment
        self._root = project_root
        self._settings = EnvironmentSettings(environment)
        self._connector = connector
        self._run = run

    def check(self) -> tuple[EnvironmentCheck, ...]:
        return (self._database(), self._allowlist(), self._liquibase(), self._accepted())

    def _database(self) -> EnvironmentCheck:
        try:
            target = self._settings.target()
            connector = self._connector(self._settings.credentials())
            with connector.connect(target) as connection:
                connection.execute("SELECT 1")
        except (SettingsUnavailableError, DatabaseUnavailableError) as error:
            return EnvironmentCheck("database", False, str(error))
        return EnvironmentCheck("database", True, f"подключение к {target} выполнено")

    def _allowlist(self) -> EnvironmentCheck:
        try:
            target = self._settings.target()
            self._settings.allowlist().require(target)
        except (SettingsUnavailableError, DatabaseNotAllowedError) as error:
            return EnvironmentCheck("allowlist", False, str(error))
        return EnvironmentCheck("allowlist", True, f"{target} входит в перечень тестовых")

    def _liquibase(self) -> EnvironmentCheck:
        try:
            version = require_liquibase(self._root, self._env, self._run)
        except LiquibaseUnavailableError as error:
            return EnvironmentCheck("liquibase", False, str(error))
        driver = driver_path(self._root, self._env).name
        return EnvironmentCheck("liquibase", True, f"Liquibase {version}, драйвер {driver}")

    def _accepted(self) -> EnvironmentCheck:
        # Существование каталога не проверяется: до первого `forge close` корня нет
        try:
            root = self._settings.accepted_root()
        except SettingsUnavailableError as error:
            return EnvironmentCheck("accepted", False, str(error))
        return EnvironmentCheck("accepted", True, f"корень принятого состояния {root.as_posix()}")
