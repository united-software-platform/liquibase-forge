"""Контракт записи операции (CQRS-001): только изменение состояния."""

from __future__ import annotations

from typing import Protocol

from forge.operation.domain.operation import Operation


class OperationWriteRepositoryInterface(Protocol):
    """Сохранить статус и причину остановки операции в её беклоге."""

    def save(self, operation: Operation) -> None: ...
