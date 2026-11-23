"""Настройки тестовой среды из переменных окружения."""

from __future__ import annotations

import posixpath
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath

from forge.shared.application.settings import DatabaseCredentials, SettingsUnavailableError
from forge.shared.domain.target_database import (
    InvalidAllowlistError,
    TargetDatabase,
    TestDatabaseAllowlist,
    parse_allowlist,
)

ACCEPTED_DIR = "FORGE_ACCEPTED_DIR"
DEFAULT_ACCEPTED_DIR = "db"
# Адрес сервера PostgreSQL по умолчанию: общий экземпляр workspace слушает localhost, его порт
# каскад mise задаёт переменной PG_PORT; вне workspace — стандартный порт. Умолчание живёт
# в инструменте, а не дублируется в конфигурации проекта
DEFAULT_HOST = "localhost"
DEFAULT_PORT = "5432"
CASCADE_PORT = "PG_PORT"


def server_port(environment: Mapping[str, str]) -> str:
    """Порт сервера PostgreSQL: `PG_PORT` из каскада mise, если задан, иначе `5432`."""
    return environment.get(CASCADE_PORT, "").strip() or DEFAULT_PORT


class EnvironmentSettings:
    """`FORGE_DB_*`, `FORGE_TEST_DB_ALLOWLIST` и `FORGE_ACCEPTED_DIR` из окружения процесса."""

    def __init__(self, environment: Mapping[str, str]) -> None:
        self._env = environment

    def target(self) -> TargetDatabase:
        """Целевая БД: хост по умолчанию `localhost`, порт — из каскада, иначе `5432`."""
        host = self._env.get("FORGE_DB_HOST", "").strip() or DEFAULT_HOST
        port = self._env.get("FORGE_DB_PORT", "").strip() or server_port(self._env)
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

    def accepted_root(self) -> Path:
        """Корень принятого состояния: относительный путь внутри корня проекта, умолчание `db`.

        Правило совпадает с проверкой шлюза Liquibase: корень, который шлюз отклонил бы
        на запасном пути отката, отклоняется сразу.
        """
        value = self._env.get(ACCEPTED_DIR, "")
        if not value:
            return Path(DEFAULT_ACCEPTED_DIR)
        if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
            raise SettingsUnavailableError(
                f"{ACCEPTED_DIR} должен быть относительным путём: {value!r}"
            )
        normalized = posixpath.normpath(value)
        if normalized == ".." or normalized.startswith("../"):
            raise SettingsUnavailableError(f"{ACCEPTED_DIR} выходит за корень проекта: {value!r}")
        return Path(normalized)

    def _required(self, name: str) -> str:
        value = self._env.get(name, "")
        if not value:
            raise SettingsUnavailableError(f"переменная окружения {name} не задана")
        return value
