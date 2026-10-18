"""Настройки тестовой среды из переменных окружения."""

from __future__ import annotations

from collections.abc import Mapping

from forge.shared.application.settings import DatabaseCredentials, SettingsUnavailableError
from forge.shared.domain.target_database import (
    InvalidAllowlistError,
    TargetDatabase,
    TestDatabaseAllowlist,
    parse_allowlist,
)


class EnvironmentSettings:
    """`FORGE_DB_*` и `FORGE_TEST_DB_ALLOWLIST` из окружения процесса."""

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

    def _required(self, name: str) -> str:
        value = self._env.get(name, "")
        if not value:
            raise SettingsUnavailableError(f"переменная окружения {name} не задана")
        return value
