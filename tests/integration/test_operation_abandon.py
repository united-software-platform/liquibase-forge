"""Отказ от операции через раннер на `lbfr-db-test`: схема возвращается к принятому состоянию.

Принятое состояние — одна операция с таблицей клиентов. Вторая операция накатывает попытку
с таблицей счетов, получает вердикт `success` и не закрывается; `forge abandon` её бросает.
После этого схема совпадает с принятой моделью, корень принятого состояния побайтово прежний,
а открытой операции нет.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import psycopg
import pytest

from forge.operation.infrastructure.accepted_state import FileAcceptedState
from tests.conftest import TestDatabase
from tests.integration.migration_support import forge, write_model
from tests.migration.models import CUSTOMER, INVOICE
from tests.migration.operation_backlog import write_operation

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("runner_configured")]

FIRST, SECOND = "20261016-120000", "20261017-153000"


def _operation(root: Path, stamp: str) -> Path:
    """Беклог операции `stamp` в следе `root`, как его ищет `forge status --latest`."""
    directory = root / "forge-model" / stamp
    directory.mkdir(parents=True)
    return write_operation(directory, subject=stamp)


def _attempt(
    capsys: pytest.CaptureFixture[str], operation: Path, tables: str, accepted: Path
) -> Path:
    """Модель и changelog первой попытки операции от принятой модели `accepted`."""
    directory = operation.parent / "attempt-1"
    directory.mkdir()
    model = write_model(directory / "model.yaml", tables)
    code, payload = forge(
        capsys,
        "generate",
        "--model", str(model),
        "--accepted", str(accepted),
        "--operation", str(operation),
        "--out", str(directory / "changelog.yaml"),
    )  # fmt: skip
    assert code == 0, payload
    return directory


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _tables(target: TestDatabase) -> set[str]:
    with psycopg.connect(target.conninfo) as connection:
        rows = connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    return {row[0] for row in rows} - {"databasechangelog", "databasechangeloglock"}


def test_abandon_returns_schema_to_accepted_state(
    capsys: pytest.CaptureFixture[str],
    trail: Path,
    target: TestDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accepted_root = trail / "db"
    backlog_root = trail / "backlog"
    monkeypatch.setenv("FORGE_ACCEPTED_DIR", accepted_root.as_posix())
    monkeypatch.setenv("BACKLOG_ROOT", backlog_root.as_posix())

    # Принятое состояние: первая операция с таблицей клиентов, накатанная на тестовую БД
    first = _operation(trail / "closed", FIRST)
    files = FileAcceptedState(accepted_root).accept(
        FIRST, str(_attempt(capsys, first, CUSTOMER, accepted_root / "model.yaml"))
    )
    code, payload = forge(capsys, "apply", "--changelog", files.master)
    assert code == 0, payload

    # Вторая операция: попытка 1 с таблицей счетов накатана, вердикт success, операция открыта
    second = _operation(backlog_root, SECOND)
    attempt = _attempt(capsys, second, CUSTOMER + INVOICE, Path(files.model))
    code, payload = forge(capsys, "apply", "--changelog", str(attempt / "changelog.yaml"))
    assert code == 0, payload
    text = second.read_text(encoding="utf-8")
    text = text.replace("  attempt_1: null\n", "  attempt_1: success\n", 1)
    text = text.replace(
        "backlog:\n  attempt_1: null\n",
        f"backlog:\n  attempt_1: backlog/forge-apply/{SECOND}-1/tasks.md\n",
        1,
    )
    second.write_text(text, encoding="utf-8")
    assert "invoice" in _tables(target)
    before = _snapshot(accepted_root)

    code, payload = forge(capsys, "abandon", "--operation", str(second), "--reason", "передумал")

    assert code == 0, payload
    assert (payload["operation"]["status"], payload["operation"]["stop_reason"]) == (
        "abandoned",
        "передумал",
    )
    rollback = json.loads((attempt / "rollback.json").read_text(encoding="utf-8"))
    assert (rollback["verdict"], rollback["verified"]) == ("success", True)
    assert _snapshot(accepted_root) == before
    assert _tables(target) == {"customer"}

    # Сверка по принятой модели: копия вне корня, чтобы reconcile.json не лёг в корень
    check = trail / "check"
    check.mkdir()
    model = shutil.copyfile(files.model, check / "model.yaml")
    changelog = shutil.copyfile(files.changelog, check / "changelog.yaml")
    code, payload = forge(capsys, "reconcile", "--model", str(model), "--changelog", str(changelog))
    assert code == 0, payload
    assert (payload["verdict"], payload["discrepancies"]) == ("success", [])

    code, payload = forge(capsys, "status", "--latest")
    assert code == 0, payload
    assert payload["operation"] is None
