"""Команды `forge env check` и `forge env up`: проверка и подготовка среды исполнения.

Команды среды не участвуют в операции: их код `2` — диагностика для владельца, а не повод
останавливать открытую операцию.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from forge.cli.contract import ExitCode, emit, environment_error
from forge.cli.parser import Parser
from forge.environment.application.check_environment.use_case import (
    CheckEnvironmentUseCase,
    CheckEnvironmentUseCaseInterface,
)
from forge.environment.application.prepare_environment.use_case import (
    PrepareEnvironmentUseCase,
    PrepareEnvironmentUseCaseInterface,
)
from forge.environment.infrastructure.database_provisioner import PostgresDatabaseProvisioner
from forge.environment.infrastructure.liquibase_driver_store import LocalLiquibaseDriverStore
from forge.operation.infrastructure.environment_probe import EnvironmentProbe
from forge.shared.application.environment import EnvironmentCheck
from forge.shared.application.settings import (
    DatabaseCredentials,
    DatabaseUnavailableError,
    LiquibaseUnavailableError,
    SettingsUnavailableError,
)
from forge.shared.infrastructure.settings import EnvironmentSettings

ADMIN_USER = "FORGE_DB_ADMIN_USER"
ADMIN_PASSWORD = "FORGE_DB_ADMIN_PASSWORD"

# Ошибки окружения подготовки — виды ошибки `error.kind` в ответе с кодом `2`
ERROR_KINDS = (
    (SettingsUnavailableError, "settings_unavailable"),
    (DatabaseUnavailableError, "database_unavailable"),
    (LiquibaseUnavailableError, "liquibase_unavailable"),
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Добавить команду `env` с глаголами `check` и `up`."""
    parser = subparsers.add_parser("env", add_help=False)
    verbs = parser.add_subparsers(dest="verb", required=True, parser_class=Parser)
    check = verbs.add_parser("check", add_help=False)
    check.set_defaults(handler=run_check)
    up = verbs.add_parser("up", add_help=False)
    up.set_defaults(handler=run_up)


def build_check() -> CheckEnvironmentUseCaseInterface:
    """Собрать проверку среды: та же проверка, что у `forge status`, корень — текущий каталог."""
    return CheckEnvironmentUseCase(EnvironmentProbe(os.environ, Path.cwd()))


def administrator(
    environment: Mapping[str, str], credentials: DatabaseCredentials
) -> DatabaseCredentials:
    """Учётные данные администратора сервера: `FORGE_DB_ADMIN_*`, иначе — целевой БД."""
    return DatabaseCredentials(
        environment.get(ADMIN_USER, "").strip() or credentials.user,
        environment.get(ADMIN_PASSWORD, "").strip() or credentials.password,
    )


def build_prepare() -> PrepareEnvironmentUseCaseInterface:
    """Собрать подготовку: база — под администратором сервера, драйвер — в `.forge/lib/` корня."""
    settings = EnvironmentSettings(os.environ)
    root = Path.cwd()
    return PrepareEnvironmentUseCase(
        PostgresDatabaseProvisioner(settings, administrator(os.environ, settings.credentials())),
        LocalLiquibaseDriverStore(root, os.environ),
    )


def run_check(
    args: argparse.Namespace, use_case: CheckEnvironmentUseCaseInterface | None = None
) -> int:
    """`0` — все проверки пройдены, `2` — какая-то не пройдена; отчёт всегда полный."""
    checks = (use_case or build_check()).execute().checks
    emit({"checks": [_payload(check) for check in checks]})
    failed = [check.name for check in checks if not check.passed]
    if not failed:
        return ExitCode.SUCCESS
    sys.stderr.write(f"forge: проверки среды не пройдены: {', '.join(failed)}\n")
    return ExitCode.ENVIRONMENT_ERROR


def run_up(
    args: argparse.Namespace, use_case: PrepareEnvironmentUseCaseInterface | None = None
) -> int:
    """`0` — среда готова, `2` — ошибка окружения: настройки, сервер или загрузка драйвера."""
    try:
        output = (use_case or build_prepare()).execute()
    except (SettingsUnavailableError, DatabaseUnavailableError, LiquibaseUnavailableError) as error:
        return environment_error(preparation_error_kind(error), str(error))
    emit(
        {
            "driver": output.driver,
            "database": output.database,
            "role_created": output.role_created,
            "database_created": output.database_created,
        }
    )
    return ExitCode.SUCCESS


def preparation_error_kind(error: Exception) -> str:
    """Вид ошибки окружения подготовки по классу исключения."""
    for error_type, kind in ERROR_KINDS:
        if isinstance(error, error_type):
            return kind
    raise error


def _payload(check: EnvironmentCheck) -> dict[str, object]:
    return {"name": check.name, "ok": check.passed, "message": check.detail}
