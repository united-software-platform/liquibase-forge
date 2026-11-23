"""Сценарии среды: подготовка идемпотентна и не трогает операцию, проверка даёт полный отчёт."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.environment.application.check_environment.use_case import CheckEnvironmentUseCase
from forge.environment.application.prepare_environment.use_case import (
    PrepareEnvironmentUseCase,
    Provisioning,
)
from forge.shared.application.environment import EnvironmentCheck
from forge.shared.application.settings import LiquibaseUnavailableError

CHECKS = (
    EnvironmentCheck("database", True, "ок"),
    EnvironmentCheck("allowlist", False, "БД вне перечня"),
    EnvironmentCheck("liquibase", True, "Liquibase 5.0.4"),
    EnvironmentCheck("accepted", True, "корень db"),
)


class _Probe:
    def __init__(self, checks: tuple[EnvironmentCheck, ...]) -> None:
        self.checks = checks
        self.calls = 0

    def check(self) -> tuple[EnvironmentCheck, ...]:
        self.calls += 1
        return self.checks


class _Driver:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def ensure(self) -> Path:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return Path(".forge/lib/postgresql-42.7.13.jar")


class _Databases:
    def __init__(self, provisioning: Provisioning, error: Exception | None = None) -> None:
        self.provisioning = provisioning
        self.error = error
        self.calls = 0

    def ensure(self) -> Provisioning:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.provisioning


def test_check_reports_every_check_as_is() -> None:
    probe = _Probe(CHECKS)

    output = CheckEnvironmentUseCase(probe).execute()

    assert output.checks == CHECKS
    assert output.ok is False
    assert probe.calls == 1


def test_check_passes_only_when_every_check_passes() -> None:
    output = CheckEnvironmentUseCase(_Probe(tuple(c for c in CHECKS if c.passed))).execute()

    assert output.ok is True
    assert [check.name for check in output.checks] == ["database", "liquibase", "accepted"]


def test_preparation_reports_driver_and_server_changes(tmp_path: Path) -> None:
    driver = _Driver()
    databases = _Databases(Provisioning("lbfr_forge", True, False))

    output = PrepareEnvironmentUseCase(databases, driver).execute()

    assert (output.driver, output.database) == ("postgresql-42.7.13.jar", "lbfr_forge")
    assert (output.role_created, output.database_created) == (True, False)
    assert (driver.calls, databases.calls) == (1, 1)


def test_preparation_is_idempotent(tmp_path: Path) -> None:
    databases = _Databases(Provisioning("lbfr_forge", False, False))

    first = PrepareEnvironmentUseCase(databases, _Driver()).execute()
    second = PrepareEnvironmentUseCase(databases, _Driver()).execute()

    assert (first.role_created, first.database_created) == (False, False)
    assert second == first


def test_driver_failure_stops_before_database() -> None:
    driver = _Driver(LiquibaseUnavailableError("не удалось загрузить драйвер"))
    databases = _Databases(Provisioning("lbfr_forge", True, True))

    with pytest.raises(LiquibaseUnavailableError, match="не удалось загрузить"):
        PrepareEnvironmentUseCase(databases, driver).execute()

    assert databases.calls == 0


def test_preparation_touches_no_operation_files(tmp_path: Path) -> None:
    """Подготовка не участвует в операции: след операций и принятое состояние не меняются."""
    trail = tmp_path / "backlog" / "forge-model" / "20261123-120000" / "tasks.md"
    trail.parent.mkdir(parents=True)
    trail.write_text("---\nstatus: running\n---\n", encoding="utf-8")
    accepted = tmp_path / "db" / "model.yaml"
    accepted.parent.mkdir()
    accepted.write_text("version: 1\ntables: []\n", encoding="utf-8")
    before = (trail.read_text(encoding="utf-8"), accepted.read_text(encoding="utf-8"))

    PrepareEnvironmentUseCase(
        _Databases(Provisioning("lbfr_forge", True, True)), _Driver()
    ).execute()

    assert (trail.read_text(encoding="utf-8"), accepted.read_text(encoding="utf-8")) == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["backlog", "db"]
