"""Сценарий наката: успех, ошибка Liquibase, БД вне перечня, недоступный шлюз."""

from __future__ import annotations

import pytest

from forge.migration.application.apply_changelog.input import ApplyChangelogInput
from forge.migration.application.apply_changelog.use_case import ApplyChangelogUseCase
from forge.migration.application.liquibase_gateway import GatewayUnavailableError
from forge.migration.application.settings import SettingsUnavailableError
from forge.migration.domain.target_database import DatabaseNotAllowedError
from forge.migration.infrastructure.environment import EnvironmentSettings
from tests.migration.fakes import FakeGateway, FakeSettings, FakeWriter

CHANGELOG = "backlog/forge-model/20261017-153000/attempt-1/changelog.yaml"
RESULT = "backlog/forge-model/20261017-153000/attempt-1/apply.json"


def test_successful_apply_writes_result_next_to_changelog() -> None:
    gateway, writer = FakeGateway(0), FakeWriter()

    output = ApplyChangelogUseCase(FakeSettings(), gateway, writer).execute(
        ApplyChangelogInput(CHANGELOG)
    )

    assert gateway.calls[0][:2] == ("update", CHANGELOG)
    assert (output.succeeded, output.exit_code, output.result_path) == (True, 0, RESULT)
    assert output.database == "lbfr-db-test:5432/t_0001"
    assert writer.documents[RESULT] == {
        "changelog": CHANGELOG,
        "database": {"host": "lbfr-db-test", "port": 5432, "name": "t_0001"},
        "request_id": "req-1",
        "exit_code": 0,
        "stdout": "out",
        "stderr": "",
    }


def test_liquibase_failure_writes_result() -> None:
    writer = FakeWriter()

    output = ApplyChangelogUseCase(FakeSettings(), FakeGateway(1), writer).execute(
        ApplyChangelogInput(CHANGELOG)
    )

    assert (output.succeeded, output.exit_code) == (False, 1)
    assert writer.documents[RESULT]["stderr"] == "ERROR: liquibase"


@pytest.mark.parametrize("allowlist", ["", "lbfr-db:5432/forge"])
def test_database_outside_allowlist_does_not_call_gateway(allowlist: str) -> None:
    gateway, writer = FakeGateway(0), FakeWriter()

    with pytest.raises(DatabaseNotAllowedError):
        ApplyChangelogUseCase(FakeSettings(allowlist), gateway, writer).execute(
            ApplyChangelogInput(CHANGELOG)
        )

    assert gateway.calls == [] and writer.documents == {}


def test_unavailable_gateway_leaves_no_result() -> None:
    writer = FakeWriter()
    gateway = FakeGateway(GatewayUnavailableError("runner_unavailable", "раннер недоступен"))

    with pytest.raises(GatewayUnavailableError):
        ApplyChangelogUseCase(FakeSettings(), gateway, writer).execute(
            ApplyChangelogInput(CHANGELOG)
        )

    assert writer.documents == {}


def test_missing_environment_is_settings_error() -> None:
    with pytest.raises(SettingsUnavailableError, match="FORGE_DB_HOST"):
        ApplyChangelogUseCase(EnvironmentSettings({}), FakeGateway(0), FakeWriter()).execute(
            ApplyChangelogInput(CHANGELOG)
        )
