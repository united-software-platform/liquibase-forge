"""Связи и уникальность через раннер на `lbfr-db-test`: накат, сверка и откат ограничений."""

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

BASE_STAMP = "20261001-090000"

# invoice ссылается на customer ниже по модели, category — на себя, line_note — составным FK
# с колонками в порядке, отличном от первичного ключа цели
LINKED = """
  - name: invoice
    columns:
      - {name: id, type: bigint}
      - {name: number, type: text, nullable: false}
      - {name: customer_id, type: uuid}
    primary_key: [id]
    unique:
      - [number]
    foreign_keys:
      - {columns: [customer_id], references: {table: customer, columns: [id]}}
  - name: customer
    columns:
      - {name: id, type: uuid}
      - {name: tenant_id, type: bigint, nullable: false}
      - {name: code, type: text, nullable: false}
    primary_key: [id]
    unique:
      - [tenant_id, code]
  - name: category
    columns:
      - {name: id, type: bigint}
      - {name: parent_id, type: bigint}
    primary_key: [id]
    foreign_keys:
      - {columns: [parent_id], references: {table: category, columns: [id]}}
  - name: line
    columns:
      - {name: invoice_id, type: bigint}
      - {name: line_no, type: integer}
    primary_key: [invoice_id, line_no]
  - name: line_note
    columns:
      - {name: id, type: bigint}
      - {name: line_no, type: integer}
      - {name: invoice, type: bigint}
    primary_key: [id]
    foreign_keys:
      - {columns: [line_no, invoice], references: {table: line, columns: [line_no, invoice_id]}}
"""

# Удалены таблица invoice с FK и набором, набор customer и FK category на себя
UNLINKED = (
    """
  - name: customer
    columns:
      - {name: id, type: uuid}
      - {name: tenant_id, type: bigint, nullable: false}
      - {name: code, type: text, nullable: false}
    primary_key: [id]
  - name: category
    columns:
      - {name: id, type: bigint}
      - {name: parent_id, type: bigint}
    primary_key: [id]
"""
    + "  - name: line\n"
    + LINKED.split("  - name: line\n", 1)[1]
)


def _generate_and_apply(
    capsys: pytest.CaptureFixture[str],
    directory: Path,
    operation: Path,
    model: Path,
    accepted: Path,
) -> Path:
    changelog = directory / "changelog.yaml"
    code, payload = forge(
        capsys,
        "generate",
        "--model", str(model),
        "--accepted", str(accepted),
        "--operation", str(operation),
        "--out", str(changelog),
    )  # fmt: skip
    assert code == 0, payload
    code, payload = forge(capsys, "apply", "--changelog", str(changelog))
    assert code == 0, payload
    return changelog


def _constraints(database: TestDatabase) -> set[tuple[str, str, str]]:
    """Ограничения схемы `public`: таблица, вид и действие при удалении у FK."""
    with psycopg.connect(database.conninfo) as connection:
        rows = connection.execute(
            "SELECT c.relname, con.contype, con.confdeltype FROM pg_constraint con "
            "JOIN pg_class c ON c.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND con.contype IN ('f', 'u')"
        ).fetchall()
    return {(table, kind, action) for table, kind, action in rows}


def test_model_with_relations_applies_and_reconciles(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    write_operation(trail, subject=STAMP)
    attempt = trail / "attempt-1"
    attempt.mkdir()
    model = write_model(attempt / "model.yaml", LINKED)
    changelog = _generate_and_apply(
        capsys, attempt, trail / "tasks.md", model, trail / "missing.yaml"
    )

    code, payload = forge(capsys, "reconcile", "--model", str(model), "--changelog", str(changelog))

    assert code == 0, payload
    assert (payload["verdict"], payload["discrepancies"]) == ("success", [])
    # Действие FK — NO ACTION (`a`), у ограничений уникальности действия нет
    assert _constraints(target) == {
        ("invoice", "u", " "),
        ("invoice", "f", "a"),
        ("customer", "u", " "),
        ("category", "f", "a"),
        ("line_note", "f", "a"),
    }


def test_dropped_relations_roll_back_through_liquibase(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    base = trail / "base"
    base.mkdir()
    write_operation(base, subject=BASE_STAMP)
    base_model = write_model(base / "model.yaml", LINKED)
    base_changelog = _generate_and_apply(
        capsys, base, base / "tasks.md", base_model, trail / "missing.yaml"
    )
    write_operation(trail, subject=STAMP, verdicts=("failure", "null", "null"), allow_drop=True)
    attempt = trail / "attempt-1"
    attempt.mkdir()
    model = write_model(attempt / "model.yaml", UNLINKED)
    changelog = _generate_and_apply(capsys, attempt, trail / "tasks.md", model, base_model)
    assert {table for table, *_ in _constraints(target)} == {"line_note"}
    code, payload = forge(capsys, "reconcile", "--model", str(model), "--changelog", str(changelog))
    assert code == 0, payload

    use_case = rollback.build_use_case(accepted_master_path=str(trail / "accepted" / "master.yaml"))
    code = rollback.run(Namespace(operation=str(trail / "tasks.md"), attempt=1), use_case)
    payload = json.loads(capsys.readouterr().out)

    assert code == 0, payload
    assert (payload["action"], payload["rolled_back"], payload["verified"]) == (
        "liquibase_rollback",
        4,
        True,
    )
    result = json.loads((attempt / "rollback.json").read_text(encoding="utf-8"))
    checks = [(c["check"], c["passed"]) for c in result["checks"]]
    assert ("foreign_key_present", True) in checks
    assert ("unique_present", True) in checks
    assert ("table_present", True) in checks
    code, payload = forge(
        capsys, "reconcile", "--model", str(base_model), "--changelog", str(base_changelog)
    )
    assert (code, payload["discrepancies"]) == (0, [])
