"""Подставные реализации контрактов Операции."""

from __future__ import annotations

from forge.operation.application.environment import EnvironmentCheck


class FakeProbe:
    """Проверка среды с заданным итогом каждой проверки."""

    def __init__(
        self,
        database: bool = True,
        allowlist: bool = True,
        runner: bool = True,
        accepted: bool = True,
    ) -> None:
        self._results = {
            "database": database,
            "allowlist": allowlist,
            "runner": runner,
            "accepted": accepted,
        }

    def check(self) -> tuple[EnvironmentCheck, ...]:
        return tuple(
            EnvironmentCheck(name, passed, "в порядке" if passed else f"{name} не в порядке")
            for name, passed in self._results.items()
        )
