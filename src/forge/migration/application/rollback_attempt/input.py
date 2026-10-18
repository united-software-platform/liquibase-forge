"""Входной контракт сценария отката попытки."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RollbackAttemptInput:
    """Беклог операции и номер попытки."""

    operation_path: str
    attempt: int
