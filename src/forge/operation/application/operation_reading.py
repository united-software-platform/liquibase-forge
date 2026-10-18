"""Контракт чтения операции (CQRS-003) и её модель чтения."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


class OperationUnavailableError(Exception):
    """Беклог операции не прочитать либо его фронтматтер не описывает операцию."""


class SeveralOpenOperationsError(Exception):
    """В следе больше одной открытой операции: навык держит открытой только одну."""

    def __init__(self, paths: tuple[str, ...]) -> None:
        super().__init__(f"открытых операций больше одной: {', '.join(paths)}")
        self.paths = paths


@dataclass(frozen=True)
class OperationRecord:
    """Значения фронтматтера беклога операции."""

    path: str
    stamp: str
    intent: str
    mode: str
    status: str
    stop_reason: str | None
    verdicts: Mapping[int, str | None]
    backlogs: Mapping[int, str | None]
    directories: Mapping[int, str]


class OperationReadRepositoryInterface(Protocol):
    """Чтение операций из следа."""

    def get(self, path: str) -> OperationRecord:
        """Операция по пути её беклога; ошибка — `OperationUnavailableError`."""
        ...

    def open_operations(self) -> tuple[str, ...]:
        """Пути беклогов операций со статусом `running` или `stopped`."""
        ...
