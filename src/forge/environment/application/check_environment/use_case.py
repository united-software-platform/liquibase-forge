"""Сценарий проверки среды исполнения: те же проверки, что `forge status`, без поиска операции."""

from __future__ import annotations

from typing import Protocol

from forge.environment.application.check_environment.output import CheckEnvironmentOutput
from forge.shared.application.environment import EnvironmentProbeInterface


class CheckEnvironmentUseCaseInterface(Protocol):
    """Проверки среды и их общий итог."""

    def execute(self) -> CheckEnvironmentOutput: ...


class CheckEnvironmentUseCase:
    """Все проверки среды, каждая независимо от остальных: отчёт всегда полный."""

    def __init__(self, probe: EnvironmentProbeInterface) -> None:
        self._probe = probe

    def execute(self) -> CheckEnvironmentOutput:
        return CheckEnvironmentOutput(self._probe.check())
