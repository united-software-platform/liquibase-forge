"""Драйвер PostgreSQL в `.forge/lib/` проекта: загрузка с проверкой контрольной суммы.

Liquibase 5.x распространяется без драйверов БД. Прежде драйвер попадал в собранный образ
Liquibase; теперь файл лежит в локальном каталоге проекта, а forge загружает его сам.
"""

from __future__ import annotations

import hashlib
import os
import re
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

from forge.shared.application.settings import (
    LiquibaseUnavailableError,
    SettingsUnavailableError,
)
from forge.shared.infrastructure.liquibase import (
    DEFAULT_DRIVER_VERSION,
    DRIVER_VERSION,
    LOCAL_DIR,
    driver_path,
    driver_version,
)

DRIVER_SHA256 = "FORGE_LIQUIBASE_DRIVER_SHA256"
# Контрольная сумма закреплённой версии драйвера: скачанный файл сверен с подписями репозитория
DEFAULT_DRIVER_SHA256 = "6e0e4cc2d8cae902084f8a2b18728b073a6fd9d1f87c9d8bff8f298c18185b93"
MAVEN = "https://repo1.maven.org/maven2/org/postgresql/postgresql"
DOWNLOAD_TIMEOUT = 120.0
_SHA256 = re.compile(r"[0-9a-f]{64}")
# Файл в `.forge/`: скрывает локальные файлы forge от git в любом проекте
# без правки его `.gitignore`
IGNORE_TEXT = "# Локальные файлы forge: драйвер Liquibase — не коммитятся\n*\n"

Fetcher = Callable[[str], bytes]


def fetch(url: str) -> bytes:
    """Загрузить файл целиком в память: на диск уходит только прошедший проверку."""
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:
        data: bytes = response.read()
    return data


def digest_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalLiquibaseDriverStore:
    """Драйвер в `.forge/lib/` корня проекта.

    Файл с верной контрольной суммой не перезагружается, с неверной — заменяется. Неудачная
    загрузка файла не оставляет.
    """

    def __init__(
        self,
        project_root: Path,
        environment: Mapping[str, str],
        fetcher: Fetcher = fetch,
    ) -> None:
        self._root = project_root
        self._environment = environment
        self._fetch = fetcher

    def ensure(self) -> Path:
        version = driver_version(self._environment)
        digest = self._digest(version)
        path = driver_path(self._root, self._environment)
        self._hide_from_git()
        if path.is_file() and digest_of(path.read_bytes()) == digest:
            return path
        try:
            data = self._fetch(f"{MAVEN}/{version}/postgresql-{version}.jar")
        except (OSError, ValueError) as error:
            raise LiquibaseUnavailableError(
                f"не удалось загрузить драйвер PostgreSQL {version}: {error}"
            ) from None
        if digest_of(data) != digest:
            raise LiquibaseUnavailableError(
                f"контрольная сумма драйвера PostgreSQL {version} не совпала: "
                f"ожидалась {digest}, получена {digest_of(data)}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        draft = path.with_name(path.name + ".tmp")
        draft.write_bytes(data)
        os.replace(draft, path)
        return path

    def _digest(self, version: str) -> str:
        """Ожидаемая сумма: заданная, для закреплённой версии — закреплённая."""
        value = self._environment.get(DRIVER_SHA256, "").strip().lower()
        if not value and version == DEFAULT_DRIVER_VERSION:
            return DEFAULT_DRIVER_SHA256
        if not value:
            raise SettingsUnavailableError(
                f"{DRIVER_VERSION} задана без {DRIVER_SHA256}: "
                "для иной версии драйвера контрольная сумма обязательна"
            )
        if not _SHA256.fullmatch(value):
            raise SettingsUnavailableError(
                f"{DRIVER_SHA256} должна быть контрольной суммой SHA-256: {value!r}"
            )
        return value

    def _hide_from_git(self) -> None:
        """Скрыть локальный каталог forge от git; существующий `.gitignore` не трогается."""
        ignore = self._root / LOCAL_DIR / ".gitignore"
        if not ignore.exists():
            ignore.parent.mkdir(parents=True, exist_ok=True)
            ignore.write_text(IGNORE_TEXT, encoding="utf-8")
