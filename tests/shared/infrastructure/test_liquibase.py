"""Нативный Liquibase: версия из `PATH`, драйвер в `.forge/lib/` и отказы среды.

Отказ называет способ устранения: `mise install` без файла Liquibase, `forge env up` без драйвера.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from forge.shared.application.settings import LiquibaseUnavailableError
from forge.shared.infrastructure.liquibase import (
    Process,
    driver_path,
    driver_version,
    liquibase_version,
    require_liquibase,
)

VERSION_OUTPUT = "\n\nLiquibase Version: 5.0.4\n"


def _completed(returncode: int = 0, stdout: str = VERSION_OUTPUT, stderr: str = "") -> Process:
    return subprocess.CompletedProcess(["liquibase"], returncode, stdout, stderr)


def _recording(
    calls: list[list[str]], outcome: Process | Exception | None = None
) -> Callable[[list[str]], Process]:
    answer: Process | Exception = _completed() if outcome is None else outcome

    def run(command: list[str]) -> Process:
        calls.append(command)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return run


def test_driver_version_defaults_to_pinned() -> None:
    assert driver_version({}) == "42.7.13"


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_driver_version_means_default(value: str) -> None:
    assert driver_version({"FORGE_LIQUIBASE_DRIVER_VERSION": value}) == "42.7.13"


def test_driver_version_from_environment() -> None:
    assert driver_version({"FORGE_LIQUIBASE_DRIVER_VERSION": " 42.7.14 "}) == "42.7.14"


def test_driver_path_in_project_lib_dir(tmp_path: Path) -> None:
    assert driver_path(tmp_path, {}) == tmp_path / ".forge" / "lib" / "postgresql-42.7.13.jar"


def test_liquibase_version_parsed() -> None:
    assert liquibase_version(_recording([])) == "5.0.4"


def test_liquibase_version_probe_command() -> None:
    calls: list[list[str]] = []

    liquibase_version(_recording(calls))

    assert calls == [["liquibase", "--version"]]


def test_liquibase_version_read_from_stderr_when_stdout_is_empty() -> None:
    run = _recording([], _completed(0, "", VERSION_OUTPUT))

    assert liquibase_version(run) == "5.0.4"


def test_liquibase_missing_names_mise_install() -> None:
    run = _recording([], FileNotFoundError("liquibase"))

    with pytest.raises(LiquibaseUnavailableError, match="mise install"):
        liquibase_version(run)


def test_liquibase_hanging_is_unavailable() -> None:
    run = _recording([], subprocess.TimeoutExpired(["liquibase", "--version"], 30))

    with pytest.raises(LiquibaseUnavailableError, match="не завершился"):
        liquibase_version(run)


def test_liquibase_unstartable_is_unavailable() -> None:
    run = _recording([], PermissionError("denied"))

    with pytest.raises(LiquibaseUnavailableError, match="denied"):
        liquibase_version(run)


@pytest.mark.parametrize(
    "outcome", [_completed(1, "", "Error: Java not found"), _completed(0, "no version here", "")]
)
def test_liquibase_failure_or_silent_output_is_unavailable(outcome: Process) -> None:
    with pytest.raises(LiquibaseUnavailableError):
        liquibase_version(_recording([], outcome))


@pytest.fixture
def driver(tmp_path: Path) -> Path:
    path = driver_path(tmp_path, {})
    path.parent.mkdir(parents=True)
    path.write_bytes(b"jar")
    return path


def test_require_liquibase_returns_version(tmp_path: Path, driver: Path) -> None:
    assert require_liquibase(tmp_path, {}, _recording([])) == "5.0.4"


def test_require_liquibase_missing_driver_names_env_up(tmp_path: Path) -> None:
    with pytest.raises(LiquibaseUnavailableError, match="forge env up"):
        require_liquibase(tmp_path, {}, _recording([]))


def test_require_liquibase_missing_executable_comes_first(tmp_path: Path, driver: Path) -> None:
    run = _recording([], FileNotFoundError("liquibase"))

    with pytest.raises(LiquibaseUnavailableError, match="mise install"):
        require_liquibase(tmp_path, {}, run)


def test_require_liquibase_uses_configured_driver_version(tmp_path: Path, driver: Path) -> None:
    run = _recording([])

    with pytest.raises(LiquibaseUnavailableError, match=r"postgresql-42\.7\.14\.jar"):
        require_liquibase(tmp_path, {"FORGE_LIQUIBASE_DRIVER_VERSION": "42.7.14"}, run)
