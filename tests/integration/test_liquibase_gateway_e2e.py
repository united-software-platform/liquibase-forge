"""Сквозная проверка шлюза Liquibase: агент пишет запрос, раннер на хосте исполняет цель.

Нужны раннер (`AGENT_RUNNER_URL`, `AGENT_RUNNER_TOKEN`) и сервер `lbfr-db-test`; без них
тесты пропускаются с причиной.
"""

from __future__ import annotations

import json
import os
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tests.conftest import TestDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUEST_PATH = PROJECT_ROOT / ".forge" / "liquibase-request.json"
RESULT_PATH = PROJECT_ROOT / ".forge" / "liquibase-result.json"
CHANGELOG = "tests/fixtures/liquibase/gateway-probe.yaml"

pytestmark = pytest.mark.integration


@pytest.fixture
def runner() -> tuple[str, str]:
    url = os.environ.get("AGENT_RUNNER_URL", "")
    token = os.environ.get("AGENT_RUNNER_TOKEN", "")
    if not url or not token:
        pytest.skip("AGENT_RUNNER_URL или AGENT_RUNNER_TOKEN не заданы: раннер не настроен")
    return url, token


def _call_gateway(runner: tuple[str, str], target: str, request: dict[str, Any]) -> Any:
    """Записать запрос, вызвать цель через раннер и вернуть файл результата."""
    REQUEST_PATH.parent.mkdir(exist_ok=True)
    REQUEST_PATH.write_text(json.dumps(request), encoding="utf-8")
    url, token = runner
    http_request = urllib.request.Request(f"{url}/run/{target}", headers={"X-Runner-Token": token})
    with urllib.request.urlopen(http_request, timeout=900) as response:
        response.read()
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    assert result["request_id"] == request["request_id"], "результат чужого запроса"
    return result


def _request(database: TestDatabase, action: str, **extra: Any) -> dict[str, Any]:
    return {
        "request_id": uuid.uuid4().hex,
        "action": action,
        "changelog": CHANGELOG,
        "host": database.host,
        "port": database.port,
        "database": database.name,
        **extra,
    }


def _probe(database: TestDatabase) -> tuple[bool, int]:
    """Есть ли таблица и сколько записей changeset в журнале Liquibase."""
    with psycopg.connect(database.conninfo) as connection:
        table = connection.execute("SELECT to_regclass('public.gateway_probe')").fetchone()
        journal = connection.execute(
            "SELECT count(*) FROM databasechangelog WHERE id = 'gateway-probe-01'"
        ).fetchone()
    assert table is not None and journal is not None
    return table[0] is not None, int(journal[0])


def test_update_then_rollback_one_changeset(
    runner: tuple[str, str], test_database: TestDatabase
) -> None:
    updated = _call_gateway(runner, "liquibase-update", _request(test_database, "update"))
    assert updated["exit_code"] == 0, updated["stderr"]
    assert _probe(test_database) == (True, 1)

    rolled_back = _call_gateway(
        runner, "liquibase-rollback", _request(test_database, "rollback", count=1)
    )
    assert rolled_back["exit_code"] == 0, rolled_back["stderr"]
    assert _probe(test_database) == (False, 0)


def test_database_outside_allowlist_is_refused(
    runner: tuple[str, str], test_database: TestDatabase
) -> None:
    request = _request(test_database, "update")
    request["host"] = os.environ.get("FORGE_DB_HOST", "lbfr-db")
    request["database"] = "forge_outside_allowlist"

    result = _call_gateway(runner, "liquibase-update", request)

    assert result["exit_code"] == 2
    assert "вне перечня тестовых" in result["stderr"]
