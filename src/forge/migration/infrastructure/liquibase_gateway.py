"""Шлюз Liquibase в процессе CLI: проверки запроса и запуск нативного Liquibase.

Прежде агент в контейнере не имел ни Liquibase, ни доступа к хосту, и запрос уходил файлом через
раннер целям `make`, а истинный код исхода — только файлом результата. Теперь CLI работает
на хосту сам: проверки и запуск выполняются в одном процессе, файлы обмена не нужны, и код
возврата Liquibase никто не искажает.

Проверки сохранены: changelog — только из проекта, учётные данные уходят Liquibase окружением,
а не аргументами процесса. Процесс Liquibase работает с рабочим каталогом вне проекта и читает
проект через search path: относительной записью попасть в проект он не может.
"""

from __future__ import annotations

import subprocess
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath

from forge.migration.application.liquibase_gateway import GatewayResult, GatewayUnavailableError
from forge.shared.application.settings import (
    DatabaseCredentials,
    TargetDatabaseSettingsInterface,
)
from forge.shared.domain.target_database import TargetDatabase
from forge.shared.infrastructure.liquibase import LIQUIBASE, driver_path

# Виды ошибки `GatewayUnavailableError`: отказ до запуска Liquibase и недоступный Liquibase
REFUSED = "gateway_refused"
UNAVAILABLE = "liquibase_unavailable"
# Предел одного наката или отката — как у прежнего вызова раннера: зависший Liquibase не вешает CLI
RUN_TIMEOUT = 900.0
# Адрес и учётные данные целевой БД Liquibase читает из окружения: в командной строке процесса
# они не видны
URL = "LIQUIBASE_COMMAND_URL"
USERNAME = "LIQUIBASE_COMMAND_USERNAME"
PASSWORD = "LIQUIBASE_COMMAND_PASSWORD"

Process = subprocess.CompletedProcess[str]
Runner = Callable[[list[str], Path, dict[str, str]], Process]


def run_process(command: list[str], cwd: Path, env: dict[str, str]) -> Process:
    """Запустить Liquibase и собрать его вывод."""
    return subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=RUN_TIMEOUT
    )


def relative_to_root(root: Path, changelog: str) -> str:
    """Абсолютный путь внутри корня проекта сделать относительным; прочий вернуть как есть."""
    path = Path(changelog)
    if path.is_absolute():
        base = root.resolve()
        resolved = path.resolve()
        if resolved.is_relative_to(base):
            return resolved.relative_to(base).as_posix()
    return path.as_posix()


def resolve_changelog(root: Path, changelog: str) -> str:
    """Проверить путь changelog и вернуть его нормализованным относительно корня проекта."""
    if PurePosixPath(changelog).is_absolute() or PureWindowsPath(changelog).is_absolute():
        raise GatewayUnavailableError(
            REFUSED, f"путь changelog должен быть относительным: {changelog}"
        )
    base = root.resolve()
    target = (base / changelog).resolve()
    if not target.is_relative_to(base):
        raise GatewayUnavailableError(
            REFUSED, f"путь changelog выходит за корень проекта: {changelog}"
        )
    if not target.is_file():
        raise GatewayUnavailableError(REFUSED, f"changelog не найден: {changelog}")
    return target.relative_to(base).as_posix()


def liquibase_environment(
    database: TargetDatabase, credentials: DatabaseCredentials
) -> dict[str, str]:
    """Переменные Liquibase: адрес и учётные данные целевой БД."""
    return {
        URL: f"jdbc:postgresql://{database.host}:{database.port}/{database.name}",
        USERNAME: credentials.user,
        PASSWORD: credentials.password,
    }


def build_command(
    driver: Path, root: Path, action: str, changelog: str, arguments: Sequence[str]
) -> list[str]:
    """Команда Liquibase: драйвер и корень проекта — глобальные параметры, действие — команда."""
    return [
        LIQUIBASE,
        f"--classpath={driver}",
        f"--search-path={root.resolve()}",
        action,
        f"--changelog-file={changelog}",
        *arguments,
    ]


class ProcessLiquibaseGateway:
    """Реализация контракта шлюза: подпроцесс `liquibase` на хосту.

    Перечень тестовых БД проверяет сценарий до вызова: в одном процессе повторная проверка
    границе не служит.
    """

    def __init__(
        self,
        project_root: Path,
        settings: TargetDatabaseSettingsInterface,
        environment: Mapping[str, str],
        run: Runner = run_process,
        new_request_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._root = project_root
        self._settings = settings
        self._environment = environment
        self._run = run
        self._new_request_id = new_request_id

    def update(self, changelog: str, database: TargetDatabase) -> GatewayResult:
        return self._execute("update", changelog, database, ())

    def rollback(self, changelog: str, database: TargetDatabase, count: int) -> GatewayResult:
        return self._execute("rollback-count", changelog, database, (f"--count={count}",))

    def _execute(
        self,
        action: str,
        changelog: str,
        database: TargetDatabase,
        arguments: Sequence[str],
    ) -> GatewayResult:
        credentials = self._settings.credentials()
        relative = resolve_changelog(self._root, relative_to_root(self._root, changelog))
        driver = driver_path(self._root, self._environment)
        if not driver.is_file():
            raise GatewayUnavailableError(
                UNAVAILABLE, f"драйвер PostgreSQL не найден: {driver} — выполните forge env up"
            )
        command = build_command(driver, self._root, action, relative, arguments)
        try:
            # Рабочий каталог вне проекта: относительная запись Liquibase попала бы сюда
            with tempfile.TemporaryDirectory(prefix="forge-liquibase-") as working:
                completed = self._run(
                    command,
                    Path(working),
                    {**self._environment, **liquibase_environment(database, credentials)},
                )
        except FileNotFoundError:
            raise GatewayUnavailableError(
                UNAVAILABLE, "liquibase не найден в PATH: выполните mise install"
            ) from None
        except subprocess.TimeoutExpired:
            raise GatewayUnavailableError(
                UNAVAILABLE, f"Liquibase не завершился за {RUN_TIMEOUT:.0f} с"
            ) from None
        except OSError as error:
            raise GatewayUnavailableError(
                UNAVAILABLE, f"не удалось запустить liquibase: {error}"
            ) from None
        exit_code = 0 if completed.returncode == 0 else 1
        return GatewayResult(self._new_request_id(), exit_code, completed.stdout, completed.stderr)
