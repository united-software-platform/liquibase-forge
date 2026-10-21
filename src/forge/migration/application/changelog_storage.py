"""Контракты записи и чтения файла changelog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from forge.migration.domain.changelog import Changelog


class ChangelogUnreadableError(Exception):
    """Файл changelog не прочитать или он не в формате `forge generate`."""


@dataclass(frozen=True)
class ChangelogSummary:
    """Что changelog делает со схемой: `id` changeset и добавляемые объекты."""

    logical_file_path: str | None
    changeset_ids: tuple[str, ...]
    tables: tuple[str, ...]
    columns: tuple[tuple[str, str], ...]


class ChangelogWriterInterface(Protocol):
    """Запись changelog в файл и удаление устаревшего файла."""

    def write(self, path: str, changelog: Changelog) -> None: ...

    def remove(self, path: str) -> None:
        """Удалить файл, если он есть."""
        ...


class ChangelogReaderInterface(Protocol):
    """Чтение changelog, построенного `forge generate`."""

    def read(self, path: str) -> ChangelogSummary:
        """Прочитать changelog; при ошибке — `ChangelogUnreadableError`."""
        ...

    def exists(self, path: str) -> bool:
        """Есть ли файл changelog."""
        ...
