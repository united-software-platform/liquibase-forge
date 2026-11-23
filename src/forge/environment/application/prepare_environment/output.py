"""Выходной контракт сценария подготовки среды."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PreparationOutput:
    """Итог подготовки: файл драйвера, целевая БД и то, что на сервере изменилось."""

    driver: str
    database: str
    role_created: bool
    database_created: bool
