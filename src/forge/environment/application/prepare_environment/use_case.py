"""Сценарий подготовки среды: целевая БД на сервере и драйвер Liquibase в проекте.

Команда подготовки не участвует в операции: меняет только файлы в `.forge/` и объекты на сервере,
след операций и принятое состояние не трогает.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from forge.environment.application.prepare_environment.output import PreparationOutput


@dataclass(frozen=True)
class Provisioning:
    """Целевая БД и то, что изменилось на сервере: создана ли роль, создана ли база."""

    database: str
    role_created: bool
    database_created: bool


class DatabaseProvisionerInterface(Protocol):
    """Роль и база целевой БД: создаются при отсутствии, существующие не меняются."""

    def ensure(self) -> Provisioning: ...


class LiquibaseDriverStoreInterface(Protocol):
    """Драйвер PostgreSQL в локальном каталоге проекта, если файла с верной суммой нет."""

    def ensure(self) -> Path: ...


class PrepareEnvironmentUseCaseInterface(Protocol):
    """Подготовка среды, идемпотентная: повторный вызов ничего не меняет."""

    def execute(self) -> PreparationOutput: ...


class PrepareEnvironmentUseCase:
    """Драйвер — затем база: на готовой среде повторный вызов ничего не создаёт заново."""

    def __init__(
        self,
        databases: DatabaseProvisionerInterface,
        driver: LiquibaseDriverStoreInterface,
    ) -> None:
        self._databases = databases
        self._driver = driver

    def execute(self) -> PreparationOutput:
        driver = self._driver.ensure()
        provisioning = self._databases.ensure()
        return PreparationOutput(
            driver.name,
            provisioning.database,
            provisioning.role_created,
            provisioning.database_created,
        )
