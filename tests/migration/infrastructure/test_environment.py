"""Настройки раннера из окружения: адрес, токен, предел ожидания."""

from __future__ import annotations

import pytest

from forge.migration.infrastructure.environment import runner_settings
from forge.migration.infrastructure.runner_gateway import RunnerSettings
from forge.shared.application.settings import SettingsUnavailableError

ENV = {"AGENT_RUNNER_URL": "http://runner:11920", "AGENT_RUNNER_TOKEN": "token"}


def test_values_from_environment() -> None:
    assert runner_settings(ENV) == RunnerSettings("http://runner:11920", "token", 900.0)


def test_runner_not_configured() -> None:
    assert runner_settings({**ENV, "AGENT_RUNNER_TOKEN": ""}) is None


def test_runner_timeout() -> None:
    assert runner_settings({**ENV, "AGENT_RUNNER_TIMEOUT": "30"}) == RunnerSettings(
        "http://runner:11920", "token", 30.0
    )
    with pytest.raises(SettingsUnavailableError):
        runner_settings({**ENV, "AGENT_RUNNER_TIMEOUT": "x"})
