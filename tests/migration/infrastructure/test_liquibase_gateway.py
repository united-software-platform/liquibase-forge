"""Шлюз Liquibase в процессе CLI: команда, рабочий каталог, учётные данные, проверки и отказы."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from forge.migration.application.liquibase_gateway import GatewayUnavailableError
from forge.migration.infrastructure.liquibase_gateway import (
    PASSWORD,
    REFUSED,
    UNAVAILABLE,
    URL,
    USERNAME,
    Process,
    ProcessLiquibaseGateway,
    Runner,
    relative_to_root,
)
from forge.shared.application.settings import DatabaseCredentials, SettingsUnavailableError
from forge.shared.domain.target_database import TargetDatabase

DATABASE = TargetDatabase("localhost", 5432, "t_0001")
MASTER = "db/changelog/master.yaml"
DRIVER = "postgresql-42.7.13.jar"


class _Settings:
    """Подставные настройки: учётные данные целевой БД."""

    def __init__(self, user: str = "forge", password: str = "secret") -> None:
        self._user = user
        self._password = password

    def credentials(self) -> DatabaseCredentials:
        if not self._user or not self._password:
            raise SettingsUnavailableError("переменная окружения FORGE_DB_USER не задана")
        return DatabaseCredentials(self._user, self._password)


class _Process:
    """Подставной запуск Liquibase: запоминает вызов и отвечает заданным кодом и диагностикой."""

    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self._returncode = returncode
        self._stderr = stderr
        self.calls: list[tuple[list[str], Path, dict[str, str]]] = []

    def __call__(self, command: list[str], cwd: Path, env: dict[str, str]) -> Process:
        self.calls.append((command, cwd, dict(env)))
        return subprocess.CompletedProcess(command, self._returncode, "out", self._stderr)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Проект с changelog в корне принятого состояния и драйвером в `.forge/lib/`."""
    master = tmp_path / MASTER
    master.parent.mkdir(parents=True)
    master.write_text("databaseChangeLog: []\n", encoding="utf-8")
    driver = tmp_path / ".forge" / "lib" / DRIVER
    driver.parent.mkdir(parents=True)
    driver.write_bytes(b"jar")
    return tmp_path


def _gateway(
    project: Path,
    process: Runner,
    environment: Mapping[str, str] | None = None,
    settings: _Settings | None = None,
) -> ProcessLiquibaseGateway:
    return ProcessLiquibaseGateway(
        project,
        settings or _Settings(),
        environment or {},
        run=process,
        new_request_id=lambda: "req-1",
    )


def _only(process: _Process) -> tuple[list[str], Path, dict[str, str]]:
    """Единственный вызов Liquibase: ровно один вызов и должен быть."""
    [call] = process.calls
    return call


def test_update_runs_native_liquibase(project: Path) -> None:
    process = _Process()

    result = _gateway(project, process).update(MASTER, DATABASE)

    [command, _, _] = _only(process)
    assert command == [
        "liquibase",
        f"--classpath={project / '.forge' / 'lib' / DRIVER}",
        f"--search-path={project.resolve()}",
        "update",
        f"--changelog-file={MASTER}",
    ]
    assert (result.request_id, result.exit_code, result.succeeded) == ("req-1", 0, True)


def test_rollback_runs_rollback_count(project: Path) -> None:
    process = _Process()

    _gateway(project, process).rollback(MASTER, DATABASE, 2)

    assert process.calls[0][0][-3:] == ["rollback-count", f"--changelog-file={MASTER}", "--count=2"]


def test_working_directory_is_outside_project(project: Path) -> None:
    process = _Process()

    _gateway(project, process).update(MASTER, DATABASE)

    [_, cwd, _] = _only(process)
    assert not cwd.is_relative_to(project)
    assert not cwd.exists()


def test_credentials_go_by_environment_not_arguments(project: Path) -> None:
    process = _Process()
    gateway = _gateway(project, process, settings=_Settings(user="app_user", password="s3cret"))

    gateway.update(MASTER, DATABASE)

    [command, _, env] = _only(process)
    assert all("s3cret" not in argument and "app_user" not in argument for argument in command)
    assert env[URL] == "jdbc:postgresql://localhost:5432/t_0001"
    assert (env[USERNAME], env[PASSWORD]) == ("app_user", "s3cret")


def test_process_environment_extends_cli_environment(project: Path) -> None:
    process = _Process()

    _gateway(project, process, {"PATH": "/tools", "LANG": "C"}).update(MASTER, DATABASE)

    [_, _, env] = _only(process)
    assert (env["PATH"], env["LANG"]) == ("/tools", "C")


def test_liquibase_failure_is_result_with_code_1(project: Path) -> None:
    process = _Process(1, "ERROR: relation exists")

    result = _gateway(project, process).update(MASTER, DATABASE)

    assert (result.exit_code, result.succeeded, result.stderr) == (
        1,
        False,
        "ERROR: relation exists",
    )


def test_any_liquibase_exit_code_is_failure(project: Path) -> None:
    result = _gateway(project, _Process(255)).update(MASTER, DATABASE)

    assert result.exit_code == 1


def test_absolute_changelog_inside_root_becomes_relative(project: Path) -> None:
    process = _Process()

    _gateway(project, process).update(str(project / MASTER), DATABASE)

    assert process.calls[0][0][-1] == f"--changelog-file={MASTER}"


@pytest.mark.parametrize(
    "changelog",
    ["/etc/master.yaml", "../master.yaml", "db/../../master.yaml", "db/changelog/missing.yaml"],
)
def test_changelog_outside_project_or_missing_is_refused(project: Path, changelog: str) -> None:
    process = _Process()

    with pytest.raises(GatewayUnavailableError) as caught:
        _gateway(project, process).update(changelog, DATABASE)

    assert caught.value.kind == REFUSED
    assert process.calls == []


def test_symlink_leading_outside_project_is_refused(project: Path, tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.yaml"
    outside.write_text("databaseChangeLog: []\n", encoding="utf-8")
    (project / "db" / "changelog" / "link.yaml").symlink_to(outside)
    process = _Process()

    with pytest.raises(GatewayUnavailableError) as caught:
        _gateway(project, process).update("db/changelog/link.yaml", DATABASE)

    assert caught.value.kind == REFUSED
    assert process.calls == []
    outside.unlink()


def test_driver_version_from_environment_is_used(project: Path) -> None:
    other = project / ".forge" / "lib" / "postgresql-42.7.14.jar"
    other.write_bytes(b"jar")
    process = _Process()

    _gateway(project, process, {"FORGE_LIQUIBASE_DRIVER_VERSION": "42.7.14"}).update(
        MASTER, DATABASE
    )

    assert f"--classpath={other}" in process.calls[0][0]


def test_driver_missing_is_unavailable(project: Path) -> None:
    (project / ".forge" / "lib" / DRIVER).unlink()
    process = _Process()

    with pytest.raises(GatewayUnavailableError) as caught:
        _gateway(project, process).update(MASTER, DATABASE)

    assert caught.value.kind == UNAVAILABLE
    assert "forge env up" in str(caught.value)
    assert process.calls == []


def _raise(error: Exception) -> Runner:
    def run(command: list[str], cwd: Path, env: dict[str, str]) -> Process:
        raise error

    return run


def test_liquibase_missing_is_unavailable(project: Path) -> None:
    with pytest.raises(GatewayUnavailableError) as caught:
        _gateway(project, _raise(FileNotFoundError("liquibase"))).update(MASTER, DATABASE)

    assert caught.value.kind == UNAVAILABLE
    assert "mise install" in str(caught.value)


def test_liquibase_unstartable_is_unavailable(project: Path) -> None:
    with pytest.raises(GatewayUnavailableError) as caught:
        _gateway(project, _raise(PermissionError("denied"))).update(MASTER, DATABASE)

    assert caught.value.kind == UNAVAILABLE
    assert "denied" in str(caught.value)


def test_liquibase_hang_is_unavailable(project: Path) -> None:
    timeout: subprocess.TimeoutExpired[str] = subprocess.TimeoutExpired(["liquibase"], 900)

    with pytest.raises(GatewayUnavailableError) as caught:
        _gateway(project, _raise(timeout)).update(MASTER, DATABASE)

    assert caught.value.kind == UNAVAILABLE
    assert "900" in str(caught.value)


def test_missing_credentials_prevent_launch(project: Path) -> None:
    process = _Process()
    gateway = _gateway(project, process, settings=_Settings(password=""))

    with pytest.raises(SettingsUnavailableError):
        gateway.update(MASTER, DATABASE)

    assert process.calls == []


def test_no_exchange_files_are_written(project: Path) -> None:
    process = _Process()

    _gateway(project, process).update(MASTER, DATABASE)

    assert [path.name for path in (project / ".forge").iterdir()] == ["lib"]


def test_relative_to_root(tmp_path: Path) -> None:
    assert relative_to_root(tmp_path, MASTER) == MASTER
    assert relative_to_root(tmp_path, str(tmp_path / "a.yaml")) == "a.yaml"
    assert relative_to_root(tmp_path, "/outside/a.yaml") == "/outside/a.yaml"
