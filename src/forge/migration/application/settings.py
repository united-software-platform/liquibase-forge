"""Контракт настроек целевой БД: адрес, учётные данные и перечень тестовых БД."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from forge.migration.domain.target_database import TargetDatabase, TestDatabaseAllowlist


class SettingsUnavailableError(Exception):
    """Настройки окружения не заданы или заданы неверно."""


@dataclass(frozen=True)
class DatabaseCredentials:
    """Учётные данные целевой БД для прямого подключения."""

    user: str
    password: str


class TargetDatabaseSettingsInterface(Protocol):
    """Целевая БД операций и перечень тестовых БД."""

    def target(self) -> TargetDatabase: ...

    def credentials(self) -> DatabaseCredentials: ...

    def allowlist(self) -> TestDatabaseAllowlist: ...
