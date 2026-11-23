"""Настройки тестовой среды: целевая БД и её умолчания, учётные данные, перечень, корень."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.shared.application.settings import SettingsUnavailableError
from forge.shared.domain.target_database import TargetDatabase
from forge.shared.infrastructure.settings import EnvironmentSettings, server_port

ENV = {
    "FORGE_DB_HOST": "localhost",
    "FORGE_DB_PORT": "5432",
    "FORGE_DB_NAME": "forge",
    "FORGE_DB_USER": "forge",
    "FORGE_DB_PASSWORD": "secret",
    "FORGE_TEST_DB_ALLOWLIST": "localhost:5432/forge",
}
WITHOUT_ADDRESS = {k: v for k, v in ENV.items() if k not in ("FORGE_DB_HOST", "FORGE_DB_PORT")}


def test_values_from_environment() -> None:
    settings = EnvironmentSettings(ENV)

    assert settings.target() == TargetDatabase("localhost", 5432, "forge")
    assert (settings.credentials().user, settings.credentials().password) == ("forge", "secret")
    assert settings.allowlist().admits(settings.target())


def test_missing_name() -> None:
    with pytest.raises(SettingsUnavailableError, match="FORGE_DB_NAME"):
        EnvironmentSettings({k: v for k, v in ENV.items() if k != "FORGE_DB_NAME"}).target()


def test_host_defaults_to_localhost() -> None:
    target = EnvironmentSettings(WITHOUT_ADDRESS).target()

    assert target == TargetDatabase("localhost", 5432, "forge")


@pytest.mark.parametrize("host", ["", "   "])
def test_blank_host_means_default(host: str) -> None:
    assert EnvironmentSettings({**WITHOUT_ADDRESS, "FORGE_DB_HOST": host}).target().host == (
        "localhost"
    )


@pytest.mark.parametrize("cascade", ["5433", " 5433 "])
def test_port_defaults_to_cascade_port(cascade: str) -> None:
    env = {**WITHOUT_ADDRESS, "PG_PORT": cascade}

    assert EnvironmentSettings(env).target().port == 5433


def test_port_defaults_to_5432_without_cascade() -> None:
    assert EnvironmentSettings(WITHOUT_ADDRESS).target().port == 5432


def test_explicit_address_wins_over_defaults() -> None:
    env = {**ENV, "FORGE_DB_HOST": "db.internal", "FORGE_DB_PORT": "6543", "PG_PORT": "1"}

    assert EnvironmentSettings(env).target() == TargetDatabase("db.internal", 6543, "forge")


def test_port_must_be_number() -> None:
    with pytest.raises(SettingsUnavailableError):
        EnvironmentSettings({**ENV, "FORGE_DB_PORT": "x"}).target()


def test_cascade_port_must_be_number() -> None:
    with pytest.raises(SettingsUnavailableError, match="FORGE_DB_PORT"):
        EnvironmentSettings({**WITHOUT_ADDRESS, "PG_PORT": "x"}).target()


@pytest.mark.parametrize(
    ("environment", "port"),
    [({}, "5432"), ({"PG_PORT": ""}, "5432"), ({"PG_PORT": "5433"}, "5433")],
)
def test_server_port(environment: dict[str, str], port: str) -> None:
    assert server_port(environment) == port


def test_invalid_allowlist_entry() -> None:
    with pytest.raises(SettingsUnavailableError):
        EnvironmentSettings({**ENV, "FORGE_TEST_DB_ALLOWLIST": "lbfr-db/forge"}).allowlist()


@pytest.mark.parametrize("value", [None, ""])
def test_accepted_root_defaults_to_db(value: str | None) -> None:
    env = ENV if value is None else {**ENV, "FORGE_ACCEPTED_DIR": value}

    assert EnvironmentSettings(env).accepted_root() == Path("db")


@pytest.mark.parametrize(
    ("value", "root"), [(".forge/db", ".forge/db"), ("./.forge/db/", ".forge/db")]
)
def test_accepted_root_from_environment(value: str, root: str) -> None:
    settings = EnvironmentSettings({**ENV, "FORGE_ACCEPTED_DIR": value})

    assert settings.accepted_root() == Path(root)


@pytest.mark.parametrize("value", ["/srv/db", "../db", "a/../../db"])
def test_accepted_root_outside_project(value: str) -> None:
    with pytest.raises(SettingsUnavailableError, match="FORGE_ACCEPTED_DIR"):
        EnvironmentSettings({**ENV, "FORGE_ACCEPTED_DIR": value}).accepted_root()
