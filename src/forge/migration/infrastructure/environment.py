"""Настройки Миграции из переменных окружения."""

from __future__ import annotations

from collections.abc import Mapping

from forge.migration.application.settings import DatabaseCredentials, SettingsUnavailableError
from forge.migration.domain.target_database import (
    InvalidAllowlistError,
    TargetDatabase,
    TestDatabaseAllowlist,
    parse_allowlist,
)
from forge.migration.infrastructure.runner_gateway import DEFAULT_TIMEOUT, RunnerSettings


class EnvironmentSettings:
    """`FORGE_DB_*`, `FORGE_TEST_DB_ALLOWLIST` и `AGENT_RUNNER_*` из окружения процесса."""

    def __init__(self, environment: Mapping[str, str]) -> None:
        self._env = environment

    def target(self) -> TargetDatabase:
        host = self._required("FORGE_DB_HOST")
        port = self._required("FORGE_DB_PORT")
        if not port.isdigit():
            raise SettingsUnavailableError(f"FORGE_DB_PORT должен быть номером порта: {port!r}")
        return TargetDatabase(host, int(port), self._required("FORGE_DB_NAME"))

    def credentials(self) -> DatabaseCredentials:
        return DatabaseCredentials(
            self._required("FORGE_DB_USER"), self._required("FORGE_DB_PASSWORD")
        )

    def allowlist(self) -> TestDatabaseAllowlist:
        try:
            return parse_allowlist(self._env.get("FORGE_TEST_DB_ALLOWLIST"))
        except InvalidAllowlistError as error:
            raise SettingsUnavailableError(str(error)) from None

    def runner(self) -> RunnerSettings | None:
        """Настройки раннера; `None`, если адрес или токен не заданы."""
        url, token = self._env.get("AGENT_RUNNER_URL", ""), self._env.get("AGENT_RUNNER_TOKEN", "")
        if not url or not token:
            return None
        timeout = self._env.get("AGENT_RUNNER_TIMEOUT", "")
        try:
            return RunnerSettings(url, token, float(timeout) if timeout else DEFAULT_TIMEOUT)
        except ValueError:
            raise SettingsUnavailableError(
                f"AGENT_RUNNER_TIMEOUT должен быть числом секунд: {timeout!r}"
            ) from None

    def _required(self, name: str) -> str:
        value = self._env.get(name, "")
        if not value:
            raise SettingsUnavailableError(f"переменная окружения {name} не задана")
        return value
