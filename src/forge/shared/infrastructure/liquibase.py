"""Нативный Liquibase: исполняемый файл в `PATH` и драйвер PostgreSQL в `.forge/lib/` проекта.

Liquibase 5.x не содержит драйверов БД: файл драйвера в локальный каталог кладёт `forge env up`,
а шлюз и проверка среды лишь находят его здесь.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from forge.shared.application.settings import (
    LiquibaseUnavailableError,
    SettingsUnavailableError,
)

LIQUIBASE = "liquibase"
# Локальный каталог forge; скрыт от git файлом `.forge/.gitignore`, который кладёт `forge env up`
LOCAL_DIR = Path(".forge")
LIB_DIR = LOCAL_DIR / "lib"
DRIVER_VERSION = "FORGE_LIQUIBASE_DRIVER_VERSION"
# Иная версия драйвера задаётся только парой переменных — версия и её контрольная сумма
DEFAULT_DRIVER_VERSION = "42.7.13"
VERSION_TIMEOUT = 30.0
_VERSION = re.compile(r"Liquibase Version:\s*(\S+)")
# Версия попадает в имя файла драйвера: цифры, латиница, точка, подчёркивание и дефис, с цифры
_DRIVER_VERSION_FORMAT = re.compile(r"[0-9][0-9A-Za-z._-]*")

Process = subprocess.CompletedProcess[str]
Runner = Callable[[list[str]], Process]


def driver_version(environment: Mapping[str, str]) -> str:
    """Версия драйвера PostgreSQL: из `FORGE_LIQUIBASE_DRIVER_VERSION`, иначе закреплённая.

    Недопустимое значение — ошибка настроек: путь к файлу строится из версии.
    """
    value = environment.get(DRIVER_VERSION, "").strip()
    if not value:
        return DEFAULT_DRIVER_VERSION
    if not _DRIVER_VERSION_FORMAT.fullmatch(value):
        raise SettingsUnavailableError(
            f"{DRIVER_VERSION} задаёт недопустимую версию драйвера: {value!r}"
        )
    return value


def driver_path(project_root: Path, environment: Mapping[str, str]) -> Path:
    """Файл драйвера в `.forge/lib/` проекта."""
    return project_root / LIB_DIR / f"postgresql-{driver_version(environment)}.jar"


def run_liquibase(command: list[str]) -> Process:
    """Выполнить команду Liquibase и собрать её вывод."""
    return subprocess.run(
        command, capture_output=True, text=True, check=False, timeout=VERSION_TIMEOUT
    )


def liquibase_version(run: Runner = run_liquibase) -> str:
    """Версия Liquibase из `PATH`.

    Без исполнимого файла или ответа — `LiquibaseUnavailableError`.
    """
    try:
        completed = run([LIQUIBASE, "--version"])
    except FileNotFoundError:
        raise LiquibaseUnavailableError(
            "liquibase не найден в PATH: выполните mise install"
        ) from None
    except subprocess.TimeoutExpired:
        raise LiquibaseUnavailableError(
            f"liquibase --version не завершился за {VERSION_TIMEOUT:.0f} с"
        ) from None
    except OSError as error:
        raise LiquibaseUnavailableError(f"не удалось запустить liquibase: {error}") from None
    match = _VERSION.search(completed.stdout) or _VERSION.search(completed.stderr)
    if completed.returncode != 0 or match is None:
        detail = (completed.stderr or completed.stdout).strip()
        raise LiquibaseUnavailableError(
            f"liquibase --version завершился с кодом {completed.returncode}: {detail}"
        )
    return match.group(1)


def require_liquibase(
    project_root: Path, environment: Mapping[str, str], run: Runner = run_liquibase
) -> str:
    """Вернуть версию Liquibase, когда исполнимый файл и драйвер на месте; иначе — ошибка среды."""
    version = liquibase_version(run)
    driver = driver_path(project_root, environment)
    if not driver.is_file():
        raise LiquibaseUnavailableError(
            f"драйвер PostgreSQL не найден: {driver} — выполните forge env up"
        )
    return version
