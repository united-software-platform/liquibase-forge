"""Настройки раннера на хосте из переменных окружения."""

from __future__ import annotations

from collections.abc import Mapping

from forge.migration.infrastructure.runner_gateway import DEFAULT_TIMEOUT, RunnerSettings
from forge.shared.application.settings import SettingsUnavailableError


def runner_settings(environment: Mapping[str, str]) -> RunnerSettings | None:
    """Настройки раннера из `AGENT_RUNNER_*`; `None`, если адрес или токен не заданы."""
    url = environment.get("AGENT_RUNNER_URL", "")
    token = environment.get("AGENT_RUNNER_TOKEN", "")
    if not url or not token:
        return None
    timeout = environment.get("AGENT_RUNNER_TIMEOUT", "")
    try:
        return RunnerSettings(url, token, float(timeout) if timeout else DEFAULT_TIMEOUT)
    except ValueError:
        raise SettingsUnavailableError(
            f"AGENT_RUNNER_TIMEOUT должен быть числом секунд: {timeout!r}"
        ) from None
