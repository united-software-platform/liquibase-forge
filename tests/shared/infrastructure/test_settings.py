"""Настройки тестовой среды: целевая БД, учётные данные, перечень."""

from __future__ import annotations

import pytest

from forge.shared.application.settings import SettingsUnavailableError
from forge.shared.domain.target_database import TargetDatabase
from forge.shared.infrastructure.settings import EnvironmentSettings

ENV = {
    "FORGE_DB_HOST": "lbfr-db",
    "FORGE_DB_PORT": "5432",
    "FORGE_DB_NAME": "forge",
    "FORGE_DB_USER": "forge",
    "FORGE_DB_PASSWORD": "secret",
    "FORGE_TEST_DB_ALLOWLIST": "lbfr-db:5432/forge",
    "AGENT_RUNNER_URL": "http://runner:11920",
    "AGENT_RUNNER_TOKEN": "token",
}


def test_values_from_environment() -> None:
    settings = EnvironmentSettings(ENV)

    assert settings.target() == TargetDatabase("lbfr-db", 5432, "forge")
    assert (settings.credentials().user, settings.credentials().password) == ("forge", "secret")
    assert settings.allowlist().admits(settings.target())


@pytest.mark.parametrize("name", ["FORGE_DB_HOST", "FORGE_DB_PORT", "FORGE_DB_NAME"])
def test_missing_target_variable(name: str) -> None:
    with pytest.raises(SettingsUnavailableError, match=name):
        EnvironmentSettings({k: v for k, v in ENV.items() if k != name}).target()


def test_port_must_be_number() -> None:
    with pytest.raises(SettingsUnavailableError):
        EnvironmentSettings({**ENV, "FORGE_DB_PORT": "x"}).target()


def test_invalid_allowlist_entry() -> None:
    with pytest.raises(SettingsUnavailableError):
        EnvironmentSettings({**ENV, "FORGE_TEST_DB_ALLOWLIST": "lbfr-db/forge"}).allowlist()
