"""Удаления через раннер на `lbfr-db-test`: накат, сверка и откат удалённых объектов."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import psycopg
import pytest

from forge.cli.commands import rollback
from tests.conftest import TestDatabase
from tests.integration.migration_support import STAMP, forge, write_model
from tests.migration.operation_backlog import write_operation

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("runner_configured")]

# Принятое состояние накатывается под другим штампом: его записи журнала не смешиваются
# с записями попытки, как у операций, принятых раньше
BASE_STAMP = "20261001-090000"

BASE = """
  - name: customer
    columns:
      - {name: id, type: uuid}
      - {name: email, type: string, length: 255, nullable: false}
    primary_key: [id]
  - name: invoice_line
    columns:
      - {name: line_no, type: integer}
      - {name: invoice_id, type: bigint}
      - {name: amount, type: decimal, precision: 12, scale: 2}
    primary_key: [invoice_id, line_no]
"""

# Удалены таблица invoice_line и колонка customer.email: changeset 01 и 02
DROP = """
  - name: customer
    columns:
      - {name: id, type: uuid}
    primary_key: [id]
"""

# Те же удаления и новая таблица payment: changeset 01, 02 и 03
DROP_AND_CREATE = (
    DROP
    + """
  - name: payment
    columns:
      - {name: id, type: uuid}
    primary_key: [id]
"""
)


def _prepare_base(capsys: pytest.CaptureFixture[str], trail: Path) -> None:
    base = trail / "base"
    base.mkdir()
    write_operation(base, subject=BASE_STAMP)
    model = write_model(base / "model.yaml", BASE)
    changelog = base / "changelog.yaml"
    code, payload = forge(
        capsys,
        "generate",
        "--model", str(model),
        "--accepted", str(trail / "missing.yaml"),
        "--operation", str(base / "tasks.md"),
        "--out", str(changelog),
    )  # fmt: skip
    assert code == 0, payload
    code, payload = forge(capsys, "apply", "--changelog", str(changelog))
    assert code == 0, payload


def _attempt(capsys: pytest.CaptureFixture[str], trail: Path, tables: str) -> tuple[Path, Path]:
    """Построить и накатить попытку 1 с удалениями: беклог с согласием, вердикт `failure`."""
    write_operation(trail, subject=STAMP, verdicts=("failure", "null", "null"), allow_drop=True)
    attempt = trail / "attempt-1"
    attempt.mkdir()
    model = write_model(attempt / "model.yaml", tables)
    changelog = attempt / "changelog.yaml"
    code, payload = forge(
        capsys,
        "generate",
        "--model", str(model),
        "--accepted", str(trail / "base" / "model.yaml"),
        "--operation", str(trail / "tasks.md"),
        "--out", str(changelog),
    )  # fmt: skip
    assert code == 0, payload
    code, payload = forge(capsys, "apply", "--changelog", str(changelog))
    assert code == 0, payload
    return model, changelog


def _rollback(capsys: pytest.CaptureFixture[str], trail: Path) -> tuple[int, dict[str, object]]:
    """Откатить попытку 1; принятый master — в следе, где его нет, а не в `db/` проекта."""
    use_case = rollback.build_use_case(accepted_master_path=str(trail / "accepted" / "master.yaml"))
    code = rollback.run(Namespace(operation=str(trail / "tasks.md"), attempt=1), use_case)
    return code, json.loads(capsys.readouterr().out)


def _schema(database: TestDatabase) -> tuple[set[str], set[tuple[str, str]]]:
    """Таблицы и колонки схемы `public`."""
    with psycopg.connect(database.conninfo) as connection:
        tables = connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
        columns = connection.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        ).fetchall()
    return {name for (name,) in tables}, {(table, column) for table, column in columns}


def test_drops_apply_reconcile_and_roll_back_through_liquibase(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    _prepare_base(capsys, trail)
    model, changelog = _attempt(capsys, trail, DROP)
    tables, columns = _schema(target)
    assert "invoice_line" not in tables and ("customer", "email") not in columns

    code, payload = forge(capsys, "reconcile", "--model", str(model), "--changelog", str(changelog))
    assert code == 0, payload
    assert (payload["verdict"], payload["discrepancies"]) == ("success", [])

    code, payload = _rollback(capsys, trail)

    assert code == 0, payload
    assert (payload["action"], payload["rolled_back"], payload["verified"]) == (
        "liquibase_rollback",
        2,
        True,
    )
    result = json.loads((trail / "attempt-1" / "rollback.json").read_text(encoding="utf-8"))
    passed = {c["check"] for c in result["checks"] if c["passed"]}
    assert {"table_present", "column_present"} <= passed
    tables, columns = _schema(target)
    assert "invoice_line" in tables and ("customer", "email") in columns


def test_partial_apply_of_drop_and_create_rolls_back_recorded_changesets(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    _prepare_base(capsys, trail)
    _attempt(capsys, trail, DROP_AND_CREATE)
    # Частичный накат: changeset 03 (создание payment) не дошёл до журнала и схемы
    with psycopg.connect(target.conninfo) as connection:
        connection.execute("DELETE FROM databasechangelog WHERE id = %s", (f"{STAMP}-03",))
        connection.execute("DROP TABLE payment")

    code, payload = _rollback(capsys, trail)

    assert code == 0, payload
    assert (payload["action"], payload["rolled_back"], payload["verified"]) == (
        "liquibase_rollback",
        2,
        True,
    )
    tables, columns = _schema(target)
    assert "invoice_line" in tables and ("customer", "email") in columns
    assert "payment" not in tables
