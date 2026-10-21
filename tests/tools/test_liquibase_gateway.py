"""Шлюз Liquibase `tools/liquibase/gateway.py`: проверка запроса, команда и файл результата.

Liquibase и Docker здесь не запускаются: исполнитель команды подменяется заглушкой.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_GATEWAY_PATH = Path(__file__).resolve().parents[2] / "tools" / "liquibase" / "gateway.py"


def _load_gateway() -> ModuleType:
    # Шлюз — самостоятельный скрипт хоста, а не модуль пакета: загружается по пути
    spec = importlib.util.spec_from_file_location("liquibase_gateway", _GATEWAY_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gateway = _load_gateway()

ENV = {
    "FORGE_DB_HOST": "lbfr-db",
    "FORGE_DB_USER": "forge",
    "FORGE_DB_PASSWORD": "forge-secret",
    "FORGE_TEST_DB_HOST": "lbfr-db-test",
    "FORGE_TEST_DB_USER": "forge_test",
    "FORGE_TEST_DB_PASSWORD": "test-secret",
    "FORGE_TEST_DB_ALLOWLIST": "lbfr-db:5432/forge, lbfr-db-test:5432/*",
}


class FakeRunner:
    """Заглушка исполнителя: запоминает вызов и возвращает заданный исход."""

    def __init__(self, returncode: int = 0, stdout: str = "ok", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[tuple[list[str], Path, dict[str, str]]] = []

    def __call__(
        self, command: list[str], cwd: Path, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, cwd, env))
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    changelog = tmp_path / "db" / "changelog" / "master.yaml"
    changelog.parent.mkdir(parents=True)
    changelog.write_text("databaseChangeLog: []\n", encoding="utf-8")
    (tmp_path / ".forge").mkdir()
    return tmp_path


def _request(**overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "request_id": "req-1",
        "action": "update",
        "changelog": "db/changelog/master.yaml",
        "host": "lbfr-db-test",
        "port": 5432,
        "database": "t_0001",
    }
    request.update(overrides)
    return {key: value for key, value in request.items() if value is not None}


def _write_request(project: Path, payload: Any) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (project / ".forge" / "liquibase-request.json").write_text(text, encoding="utf-8")


def _execute(
    project: Path,
    action: str = "update",
    env: dict[str, str] | None = None,
    runner: FakeRunner | None = None,
) -> tuple[Any, FakeRunner]:
    fake = runner or FakeRunner()
    result = gateway.execute(action, project, ENV if env is None else env, fake)
    return result, fake


def _assert_refused(result: Any, runner: FakeRunner, fragment: str) -> None:
    assert result.exit_code == 2
    assert fragment in result.stderr
    assert runner.calls == [], "Liquibase не должен запускаться при отказе шлюза"


# --- Корректные запросы -------------------------------------------------------------------


def test_update_runs_liquibase_on_allowed_database(project: Path) -> None:
    _write_request(project, _request())

    result, runner = _execute(project)

    assert (result.request_id, result.action, result.exit_code) == ("req-1", "update", 0)
    assert result.stdout == "ok"
    assert len(runner.calls) == 1


def test_wildcard_admits_any_database_of_server(project: Path) -> None:
    _write_request(project, _request(database="t_0001"))

    result, _ = _execute(project, env={**ENV, "FORGE_TEST_DB_ALLOWLIST": "lbfr-db-test:5432/*"})

    assert result.exit_code == 0


def test_rollback_runs_rollback_count(project: Path) -> None:
    _write_request(project, _request(action="rollback", count=2))

    result, runner = _execute(project, action="rollback")

    assert result.exit_code == 0
    command = runner.calls[0][0]
    assert command[-3:] == [
        "rollback-count",
        "--count=2",
        "--changelog-file=db/changelog/master.yaml",
    ]


def test_liquibase_failure_gives_code_1_with_diagnostics(project: Path) -> None:
    _write_request(project, _request())

    result, _ = _execute(project, runner=FakeRunner(returncode=1, stderr="Migration failed"))

    assert (result.request_id, result.exit_code) == ("req-1", 1)
    assert result.stderr == "Migration failed"


# --- Отказ по составу запроса ---------------------------------------------------------------


def test_missing_request_file_is_refused(project: Path) -> None:
    result, runner = _execute(project)

    _assert_refused(result, runner, "нет файла запроса")
    assert result.request_id is None


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ("{не json", "не является JSON"),
        ("[1, 2]", "JSON-объект"),
        (_request(action="drop"), "действие должно быть"),
        (_request(changelog=None), "нет полей: changelog"),
        ({**_request(), "password": "x"}, "лишние поля: password"),
        (_request(count=1), "лишние поля: count"),
        (_request(host=""), "host должно быть непустой строкой"),
        (_request(port="5432"), "port должно быть номером порта"),
        (_request(port=True), "port должно быть номером порта"),
        (_request(port=70000), "port должно быть номером порта"),
    ],
)
def test_malformed_request_is_refused(project: Path, payload: Any, fragment: str) -> None:
    _write_request(project, payload)

    result, runner = _execute(project)

    _assert_refused(result, runner, fragment)


def test_refusal_keeps_current_request_id(project: Path) -> None:
    (project / ".forge" / "liquibase-result.json").write_text(
        json.dumps({"request_id": "req-old", "exit_code": 0}), encoding="utf-8"
    )
    _write_request(project, _request(request_id="req-new", host=""))

    result, _ = _execute(project)

    assert (result.request_id, result.exit_code) == ("req-new", 2)


# --- Отказ по пути changelog ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("changelog", "fragment"),
    [
        ("/etc/passwd", "должен быть относительным"),
        ("../outside.yaml", "выходит за корень проекта"),
        ("db/../../outside.yaml", "выходит за корень проекта"),
        ("db/changelog/missing.yaml", "changelog не найден"),
        ("db/changelog", "changelog не найден"),
    ],
)
def test_changelog_outside_project_is_refused(project: Path, changelog: str, fragment: str) -> None:
    (project.parent / "outside.yaml").write_text("databaseChangeLog: []\n", encoding="utf-8")
    _write_request(project, _request(changelog=changelog))

    result, runner = _execute(project)

    _assert_refused(result, runner, fragment)


def test_changelog_is_normalized_inside_project(project: Path) -> None:
    _write_request(project, _request(changelog="db/./changelog/../changelog/master.yaml"))

    _, runner = _execute(project)

    assert runner.calls[0][0][-1] == "--changelog-file=db/changelog/master.yaml"


# --- Отказ по перечню тестовых БД ------------------------------------------------------------


def test_database_outside_allowlist_is_refused(project: Path) -> None:
    _write_request(project, _request(host="lbfr-db", database="other"))

    result, runner = _execute(project)

    _assert_refused(result, runner, "БД вне перечня тестовых: lbfr-db:5432/other")


def test_other_port_is_outside_allowlist(project: Path) -> None:
    _write_request(project, _request(port=5433))

    result, runner = _execute(project)

    _assert_refused(result, runner, "БД вне перечня тестовых")


@pytest.mark.parametrize("allowlist", [None, "", " , "])
def test_empty_allowlist_refuses_any_request(project: Path, allowlist: str | None) -> None:
    env = {key: value for key, value in ENV.items() if key != "FORGE_TEST_DB_ALLOWLIST"}
    if allowlist is not None:
        env["FORGE_TEST_DB_ALLOWLIST"] = allowlist
    _write_request(project, _request())

    result, runner = _execute(project, env=env)

    _assert_refused(result, runner, "FORGE_TEST_DB_ALLOWLIST пуст")


@pytest.mark.parametrize("entry", ["lbfr-db-test/t_1", "lbfr-db-test:port/t_1", ":5432/t_1"])
def test_malformed_allowlist_entry_is_refused(project: Path, entry: str) -> None:
    _write_request(project, _request())

    result, runner = _execute(project, env={**ENV, "FORGE_TEST_DB_ALLOWLIST": entry})

    _assert_refused(result, runner, "не в формате хост:порт/имя")


# --- Отказ по числу отката -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "fragment"),
    [
        (None, "нет полей: count"),
        (0, "целым положительным"),
        (-1, "целым положительным"),
        ("2", "целым положительным"),
        (1.5, "целым положительным"),
    ],
)
def test_rollback_without_positive_count_is_refused(
    project: Path, count: Any, fragment: str
) -> None:
    _write_request(project, _request(action="rollback", count=count))

    result, runner = _execute(project, action="rollback")

    _assert_refused(result, runner, fragment)


# --- Отказ по действию цели ------------------------------------------------------------------


def test_target_and_request_actions_must_match(project: Path) -> None:
    _write_request(project, _request(action="update"))

    result, runner = _execute(project, action="rollback")

    _assert_refused(result, runner, "вызвана для действия rollback")


def test_unknown_target_action_is_refused(project: Path) -> None:
    _write_request(project, _request())

    result, runner = _execute(project, action="drop")

    _assert_refused(result, runner, "неизвестное действие цели")


# --- Учётные данные ----------------------------------------------------------------------------


def test_host_matching_neither_server_is_refused(project: Path) -> None:
    _write_request(project, _request(host="elsewhere"))

    result, runner = _execute(project, env={**ENV, "FORGE_TEST_DB_ALLOWLIST": "elsewhere:5432/*"})

    _assert_refused(result, runner, "не совпадает ни с FORGE_DB_HOST, ни с FORGE_TEST_DB_HOST")


def test_missing_credentials_are_refused(project: Path) -> None:
    env = {key: value for key, value in ENV.items() if key != "FORGE_TEST_DB_PASSWORD"}
    _write_request(project, _request())

    result, runner = _execute(project, env=env)

    _assert_refused(result, runner, "FORGE_TEST_DB_USER и FORGE_TEST_DB_PASSWORD")


@pytest.mark.parametrize(
    ("host", "database", "user", "password"),
    [
        ("lbfr-db-test", "t_0001", "forge_test", "test-secret"),
        ("lbfr-db", "forge", "forge", "forge-secret"),
    ],
)
def test_credentials_selected_by_host(
    project: Path, host: str, database: str, user: str, password: str
) -> None:
    _write_request(project, _request(host=host, database=database))

    _, runner = _execute(project)

    env = runner.calls[0][2]
    assert env["LIQUIBASE_COMMAND_URL"] == f"jdbc:postgresql://{host}:5432/{database}"
    assert env["LIQUIBASE_COMMAND_USERNAME"] == user
    assert env["LIQUIBASE_COMMAND_PASSWORD"] == password


# --- Состав команды ------------------------------------------------------------------------


def test_update_command_composition(project: Path) -> None:
    _write_request(project, _request())

    _, runner = _execute(project)

    command, cwd, _ = runner.calls[0]
    assert cwd == project
    assert command == [
        "docker",
        "compose",
        "run",
        "--rm",
        "-T",
        "-e",
        "LIQUIBASE_COMMAND_URL",
        "-e",
        "LIQUIBASE_COMMAND_USERNAME",
        "-e",
        "LIQUIBASE_COMMAND_PASSWORD",
        "lbfr-liquibase",
        "update",
        "--changelog-file=db/changelog/master.yaml",
    ]


def test_password_is_not_in_command_arguments(project: Path) -> None:
    _write_request(project, _request())

    _, runner = _execute(project)

    assert not any("test-secret" in argument for argument in runner.calls[0][0])


def test_docker_missing_is_environment_error(project: Path) -> None:
    def broken_runner(
        command: list[str], cwd: Path, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("docker")

    _write_request(project, _request())

    result = gateway.execute("update", project, ENV, broken_runner)

    assert (result.request_id, result.exit_code) == ("req-1", 2)
    assert "не удалось запустить docker" in result.stderr


# --- Файл результата -----------------------------------------------------------------------


def test_previous_result_is_removed_before_execution(project: Path) -> None:
    result_path = project / ".forge" / "liquibase-result.json"
    result_path.write_text("{}", encoding="utf-8")
    seen: list[bool] = []

    def runner(
        command: list[str], cwd: Path, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        seen.append(result_path.exists())
        return subprocess.CompletedProcess(command, 0, "", "")

    _write_request(project, _request())

    gateway.execute("update", project, ENV, runner)

    assert seen == [False]


def test_result_file_written_on_refusal(project: Path) -> None:
    _write_request(project, _request(request_id="req-7", changelog="../x.yaml"))
    result, _ = _execute(project)

    gateway.write_result(project, result)

    written = json.loads((project / ".forge" / "liquibase-result.json").read_text("utf-8"))
    assert written["request_id"] == "req-7"
    assert written["action"] == "update"
    assert written["exit_code"] == 2
    assert set(written) == {"request_id", "action", "exit_code", "stdout", "stderr"}
    assert not (project / ".forge" / "liquibase-result.json.tmp").exists()


def test_result_directory_created_when_missing(tmp_path: Path) -> None:
    result = gateway.Result(None, "update", 2, "", "gateway: нет файла запроса")

    gateway.write_result(tmp_path, result)

    assert (tmp_path / ".forge" / "liquibase-result.json").is_file()


def test_result_hides_exchange_from_git(tmp_path: Path) -> None:
    gateway.write_result(tmp_path, gateway.Result(None, "update", 2, "", "нет файла запроса"))

    lines = (tmp_path / ".forge" / ".gitignore").read_text("utf-8").splitlines()
    assert "*" in lines


def test_existing_exchange_ignore_is_kept_by_gateway(tmp_path: Path) -> None:
    (tmp_path / ".forge").mkdir()
    (tmp_path / ".forge" / ".gitignore").write_text("liquibase-*.json\n", encoding="utf-8")

    gateway.write_result(tmp_path, gateway.Result(None, "update", 2, "", "нет файла запроса"))

    assert (tmp_path / ".forge" / ".gitignore").read_text("utf-8") == "liquibase-*.json\n"


def test_exchange_ignore_text_matches_forge() -> None:
    from forge.migration.infrastructure.runner_gateway import EXCHANGE_IGNORE_TEXT

    assert gateway.EXCHANGE_IGNORE_TEXT == EXCHANGE_IGNORE_TEXT
