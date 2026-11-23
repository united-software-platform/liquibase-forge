"""Контракт проверки среды исполнения — общий для `forge status` и `forge env check`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EnvironmentCheck:
    """Итог одной проверки: `database`, `allowlist`, `liquibase` или `accepted`."""

    name: str
    passed: bool
    detail: str


class EnvironmentProbeInterface(Protocol):
    """Проверить среду; каждая проверка выполняется независимо от остальных."""

    def check(self) -> tuple[EnvironmentCheck, ...]: ...
