"""Выходной контракт сценария статуса."""

from __future__ import annotations

from dataclasses import dataclass

from forge.operation.application.views import OperationView
from forge.shared.application.environment import EnvironmentCheck


@dataclass(frozen=True)
class GetStatusOutput:
    """Операция (нет открытой — `None`), проверки среды и их общий итог."""

    operation: OperationView | None
    checks: tuple[EnvironmentCheck, ...]
    environment_ok: bool
