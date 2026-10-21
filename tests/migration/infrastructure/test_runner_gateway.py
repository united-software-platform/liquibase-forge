"""Клиент шлюза: файл запроса, вызов раннера, исходы по файлу результата."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from forge.migration.application.liquibase_gateway import GatewayUnavailableError
from forge.migration.infrastructure.runner_gateway import (
    EXCHANGE_IGNORE,
    REQUEST_PATH,
    RESULT_PATH,
    RunnerLiquibaseGateway,
)
from forge.shared.application.settings import RunnerUnavailableError
from forge.shared.domain.target_database import TargetDatabase
from forge.shared.infrastructure.runner import RunnerSettings

DATABASE = TargetDatabase("lbfr-db-test", 5432, "t_0001")
RUNNER = RunnerSettings("http://runner:11920", "secret")


class _Runner:
    """Подставной раннер: запоминает цели и пишет заданный файл результата."""

    def __init__(self, root: Path, result: dict[str, Any] | None, same_id: bool = True) -> None:
        self.root = root
        self.result = result
        self.same_id = same_id
        self.targets: list[str] = []

    def __call__(self, settings: RunnerSettings, target: str) -> None:
        self.targets.append(target)
        if self.result is None:
            return
        request = json.loads((self.root / REQUEST_PATH).read_text(encoding="utf-8"))
        result = {"request_id": request["request_id"] if self.same_id else "other", **self.result}
        (self.root / RESULT_PATH).write_text(json.dumps(result), encoding="utf-8")


def _gateway(root: Path, runner: _Runner) -> RunnerLiquibaseGateway:
    return RunnerLiquibaseGateway(root, RUNNER, call=runner, new_request_id=lambda: "req-1")


def test_update_writes_request_and_returns_result(tmp_path: Path) -> None:
    runner = _Runner(tmp_path, {"exit_code": 0, "stdout": "ok", "stderr": ""})

    result = _gateway(tmp_path, runner).update("backlog/attempt-1/changelog.yaml", DATABASE)

    assert runner.targets == ["liquibase-update"]
    assert json.loads((tmp_path / REQUEST_PATH).read_text(encoding="utf-8")) == {
        "request_id": "req-1",
        "action": "update",
        "changelog": "backlog/attempt-1/changelog.yaml",
        "host": "lbfr-db-test",
        "port": 5432,
        "database": "t_0001",
    }
    assert (result.request_id, result.exit_code, result.stdout, result.succeeded) == (
        "req-1",
        0,
        "ok",
        True,
    )


def test_rollback_passes_count(tmp_path: Path) -> None:
    runner = _Runner(tmp_path, {"exit_code": 0, "stdout": "", "stderr": ""})

    _gateway(tmp_path, runner).rollback("c.yaml", DATABASE, 2)

    assert runner.targets == ["liquibase-rollback"]
    request = json.loads((tmp_path / REQUEST_PATH).read_text(encoding="utf-8"))
    assert (request["action"], request["count"]) == ("rollback", 2)


def test_absolute_changelog_inside_root_becomes_relative(tmp_path: Path) -> None:
    runner = _Runner(tmp_path, {"exit_code": 0, "stdout": "", "stderr": ""})

    _gateway(tmp_path, runner).update(str(tmp_path / "db" / "changelog" / "master.yaml"), DATABASE)

    request = json.loads((tmp_path / REQUEST_PATH).read_text(encoding="utf-8"))
    assert request["changelog"] == "db/changelog/master.yaml"


def test_liquibase_failure_is_result_with_code_1(tmp_path: Path) -> None:
    runner = _Runner(tmp_path, {"exit_code": 1, "stdout": "", "stderr": "ERROR: relation exists"})

    result = _gateway(tmp_path, runner).update("c.yaml", DATABASE)

    assert (result.exit_code, result.succeeded, result.stderr) == (
        1,
        False,
        "ERROR: relation exists",
    )


@pytest.mark.parametrize(
    ("result", "same_id", "kind"),
    [
        (
            {"exit_code": 2, "stdout": "", "stderr": "gateway: БД вне перечня"},
            True,
            "gateway_refused",
        ),
        (None, True, "gateway_result_invalid"),
        ({"exit_code": 0, "stdout": "", "stderr": ""}, False, "gateway_result_invalid"),
        ({"exit_code": 7, "stdout": "", "stderr": ""}, True, "gateway_result_invalid"),
    ],
)
def test_unavailable_outcomes(
    tmp_path: Path, result: dict[str, Any] | None, same_id: bool, kind: str
) -> None:
    runner = _Runner(tmp_path, result, same_id=same_id)

    with pytest.raises(GatewayUnavailableError) as caught:
        _gateway(tmp_path, runner).update("c.yaml", DATABASE)

    assert caught.value.kind == kind


def test_stale_result_of_previous_request_is_rejected(tmp_path: Path) -> None:
    (tmp_path / RESULT_PATH).parent.mkdir()
    (tmp_path / RESULT_PATH).write_text(json.dumps({"request_id": "old", "exit_code": 0}), "utf-8")

    with pytest.raises(GatewayUnavailableError) as caught:
        _gateway(tmp_path, _Runner(tmp_path, None)).update("c.yaml", DATABASE)

    assert caught.value.kind == "gateway_result_invalid"


def test_runner_not_configured(tmp_path: Path) -> None:
    gateway = RunnerLiquibaseGateway(tmp_path, None, call=_Runner(tmp_path, None))

    with pytest.raises(GatewayUnavailableError) as caught:
        gateway.update("c.yaml", DATABASE)

    assert caught.value.kind == "runner_unavailable"


def test_runner_failure_becomes_gateway_unavailable(tmp_path: Path) -> None:
    def refuse(settings: RunnerSettings, target: str) -> None:
        raise RunnerUnavailableError("раннер недоступен")

    gateway = RunnerLiquibaseGateway(tmp_path, RUNNER, call=refuse)

    with pytest.raises(GatewayUnavailableError) as caught:
        gateway.update("c.yaml", DATABASE)

    assert caught.value.kind == "runner_unavailable"


def test_first_request_hides_exchange_from_git(tmp_path: Path) -> None:
    runner = _Runner(tmp_path, {"exit_code": 0, "stdout": "ok", "stderr": ""})

    _gateway(tmp_path, runner).update("backlog/attempt-1/changelog.yaml", DATABASE)

    lines = (tmp_path / EXCHANGE_IGNORE).read_text(encoding="utf-8").splitlines()
    assert "*" in lines


def test_existing_exchange_ignore_is_kept(tmp_path: Path) -> None:
    (tmp_path / ".forge").mkdir()
    (tmp_path / EXCHANGE_IGNORE).write_text("liquibase-*.json\n", encoding="utf-8")
    runner = _Runner(tmp_path, {"exit_code": 0, "stdout": "ok", "stderr": ""})

    _gateway(tmp_path, runner).update("backlog/attempt-1/changelog.yaml", DATABASE)

    assert (tmp_path / EXCHANGE_IGNORE).read_text(encoding="utf-8") == "liquibase-*.json\n"
