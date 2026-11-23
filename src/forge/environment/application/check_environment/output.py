"""Выходной контракт сценария проверки среды."""

from __future__ import annotations

from dataclasses import dataclass

from forge.shared.application.environment import EnvironmentCheck


@dataclass(frozen=True)
class CheckEnvironmentOutput:
    """Проверки среды и их общий итог."""

    checks: tuple[EnvironmentCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.passed for check in self.checks)
