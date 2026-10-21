"""Входные контракты остановки и продолжения операции."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StopOperationInput:
    """Беклог операции и причина остановки."""

    operation_path: str
    reason: str


@dataclass(frozen=True)
class ResumeOperationInput:
    """Беклог операции."""

    operation_path: str
