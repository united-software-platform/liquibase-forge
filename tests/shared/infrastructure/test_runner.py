"""Раннер: настройки из окружения и вызов цели по HTTP."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from forge.shared.application.settings import RunnerUnavailableError, SettingsUnavailableError
from forge.shared.infrastructure.runner import RunnerSettings, call_runner, runner_settings

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


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        status = 200 if self.headers.get("X-Runner-Token") == "secret" else 403
        self.send_response(status)
        self.end_headers()
        self.wfile.write(f"exit: 0 {self.path}".encode())

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def http_runner() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_call_runner_succeeds(http_runner: str) -> None:
    call_runner(RunnerSettings(http_runner, "secret", 5), "liquibase-update")


def test_call_runner_rejected_token(http_runner: str) -> None:
    with pytest.raises(RunnerUnavailableError, match="HTTP 403"):
        call_runner(RunnerSettings(http_runner, "wrong", 5), "liquibase-update")


def test_call_runner_unreachable() -> None:
    with pytest.raises(RunnerUnavailableError, match="недоступен"):
        call_runner(RunnerSettings("http://127.0.0.1:9", "secret", 2), "liquibase-update")
