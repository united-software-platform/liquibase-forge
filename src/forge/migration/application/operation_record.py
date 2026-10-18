"""Контракт чтения записи об операции из её беклога.

Беклог операции принадлежит контексту Операция; Миграции из него нужны только штамп,
вердикт попытки и каталог попытки.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from forge.migration.domain.stamp import OperationStamp


class OperationRecordUnavailableError(Exception):
    """Беклог операции не прочитать или в нём нет нужных значений."""


@dataclass(frozen=True)
class OperationRecord:
    """Штамп операции, вердикты попыток и каталог следа операции."""

    stamp: OperationStamp
    verdicts: Mapping[int, str | None]
    trail_directory: str

    def verdict(self, attempt: int) -> str | None:
        """Вердикт попытки: `success`, `failure` либо `None`, пока сверки не было."""
        return self.verdicts.get(attempt)

    def attempt_directory(self, attempt: int) -> str:
        """Каталог артефактов попытки по раскладке следа."""
        return f"{self.trail_directory}/attempt-{attempt}"


class OperationRecordReaderInterface(Protocol):
    """Чтение записи об операции по пути её беклога."""

    def read(self, path: str) -> OperationRecord:
        """Прочитать беклог; при ошибке — `OperationRecordUnavailableError`."""
        ...
