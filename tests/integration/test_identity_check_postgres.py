"""Генерация значения и перечни значений через раннер на `lbfr-db-test`: накат, сверка, откат."""

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

# Перечни у всех четырёх типов, перечень из одного значения и значение с кавычкой внутри
EVENT = """
  - name: event
    columns:
      - {name: id, type: bigint, generated: identity}
      - {name: source, type: string, length: 16, nullable: false, check: [collector, manual]}
      - {name: channel, type: text, check: ["o'clock", web]}
      - {name: priority, type: integer, check: [1, 2, 3]}
      - {name: weight, type: bigint, check: [1, 3000000000, -5]}
      - {name: kind, type: text, check: [single]}
    primary_key: [id]
  - name: task
    columns:
      - {name: code, type: text}
      - {name: seq_no, type: integer, generated: identity}
    primary_key: [code]
"""
WIDER = EVENT.replace("check: [collector, manual]", "check: [collector, manual, import]")


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


def _apply_event(
    capsys: pytest.CaptureFixture[str], trail: Path, tables: str = EVENT
) -> tuple[Path, Path]:
    write_operation(trail, subject=STAMP)
    attempt = trail / "attempt-1"
    attempt.mkdir()
    model = write_model(attempt / "model.yaml", tables)
    return model, _generate_and_apply(capsys, attempt, trail / "tasks.md", model, trail / "none")


def _identity(database: TestDatabase, table: str, column: str) -> str:
    with psycopg.connect(database.conninfo) as connection:
        row = connection.execute(
            "SELECT a.attidentity FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            "WHERE c.relname = %s AND a.attname = %s",
            (table, column),
        ).fetchone()
    assert row is not None
    return str(row[0])


def _check_names(database: TestDatabase) -> set[str]:
    with psycopg.connect(database.conninfo) as connection:
        rows = connection.execute(
            "SELECT conname FROM pg_constraint con JOIN pg_namespace n ON n.oid = con.connamespace "
            "WHERE n.nspname = 'public' AND con.contype = 'c'"
        ).fetchall()
    return {str(name) for (name,) in rows}


def _rejects(database: TestDatabase, sql: str) -> bool:
    with psycopg.connect(database.conninfo) as connection:
        try:
            connection.execute(sql)
        except psycopg.errors.CheckViolation:
            return True
    return False


def test_identity_key_is_generated_by_default(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    _apply_event(capsys, trail)

    assert _identity(target, "event", "id") == "d"
    assert _identity(target, "task", "seq_no") == "d"
    with psycopg.connect(target.conninfo) as connection:
        generated = connection.execute(
            "INSERT INTO event (source) VALUES ('manual') RETURNING id"
        ).fetchone()
        explicit = connection.execute(
            "INSERT INTO event (id, source) VALUES (100, 'collector') RETURNING id"
        ).fetchone()
    assert generated is not None and generated[0] >= 1
    assert explicit == (100,)


def test_identity_column_added_to_table_with_rows(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    plain = """
  - name: task
    columns:
      - {name: code, type: text}
    primary_key: [code]
"""
    base = trail / "base"
    base.mkdir()
    write_operation(base, subject=BASE_STAMP)
    base_model = write_model(base / "model.yaml", plain)
    _generate_and_apply(capsys, base, base / "tasks.md", base_model, trail / "none")
    with psycopg.connect(target.conninfo) as connection:
        connection.execute("INSERT INTO task (code) VALUES ('a'), ('b')")
    write_operation(trail, subject=STAMP)
    attempt = trail / "attempt-1"
    attempt.mkdir()
    model = write_model(
        attempt / "model.yaml",
        plain.replace(
            "    primary_key",
            "      - {name: seq_no, type: integer, generated: identity}\n    primary_key",
        ),
    )

    _generate_and_apply(capsys, attempt, trail / "tasks.md", model, base_model)

    with psycopg.connect(target.conninfo) as connection:
        values = connection.execute("SELECT seq_no FROM task ORDER BY seq_no").fetchall()
    assert [value for (value,) in values] == [1, 2]


def test_check_lists_reject_values_outside_and_allow_null(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    _apply_event(capsys, trail)

    insert = "INSERT INTO event (source, channel, priority, weight, kind) VALUES "
    assert _rejects(target, insert + "('robot', NULL, NULL, NULL, NULL)")
    assert _rejects(target, insert + "('manual', 'api', NULL, NULL, NULL)")
    assert _rejects(target, insert + "('manual', NULL, 4, NULL, NULL)")
    assert _rejects(target, insert + "('manual', NULL, NULL, 2, NULL)")
    assert _rejects(target, insert + "('manual', NULL, NULL, NULL, 'double')")
    assert not _rejects(target, insert + "('manual', 'o''clock', 3, 3000000000, 'single')")
    assert not _rejects(target, insert + "('collector', NULL, NULL, NULL, NULL)")


def test_reconcile_check_lists_and_identity_without_discrepancies(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    model, changelog = _apply_event(capsys, trail)

    code, payload = forge(capsys, "reconcile", "--model", str(model), "--changelog", str(changelog))

    assert code == 0, payload
    assert (payload["verdict"], payload["discrepancies"]) == ("success", [])


def test_reconcile_finds_expression_check_and_always_identity(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    model, changelog = _apply_event(capsys, trail)
    with psycopg.connect(target.conninfo) as connection:
        connection.execute("ALTER TABLE event ADD CONSTRAINT manual_positive CHECK (priority > 0)")
        connection.execute("ALTER TABLE task ALTER COLUMN seq_no SET GENERATED ALWAYS")

    code, payload = forge(capsys, "reconcile", "--model", str(model), "--changelog", str(changelog))

    assert code == 1, payload
    found = [(d["kind"], d["table"], d["actual"]) for d in payload["discrepancies"]]
    assert found == [
        ("check_unexpected", "event", "CHECK ((priority > 0))"),
        ("column_generated_mismatch", "task", "identity_always"),
    ]


def test_check_rollback_restores_previous_list(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    base = trail / "base"
    base.mkdir()
    write_operation(base, subject=BASE_STAMP)
    base_model = write_model(base / "model.yaml", EVENT)
    base_changelog = _generate_and_apply(
        capsys, base, base / "tasks.md", base_model, trail / "none"
    )
    before = _check_names(target)
    write_operation(trail, subject=STAMP, verdicts=("failure", "null", "null"))
    attempt = trail / "attempt-1"
    attempt.mkdir()
    model = write_model(attempt / "model.yaml", WIDER)
    _generate_and_apply(capsys, attempt, trail / "tasks.md", model, base_model)
    assert _check_names(target) != before

    use_case = rollback.build_use_case(accepted_master_path=str(trail / "accepted" / "master.yaml"))
    code = rollback.run(Namespace(operation=str(trail / "tasks.md"), attempt=1), use_case)
    payload = json.loads(capsys.readouterr().out)

    assert code == 0, payload
    assert (payload["action"], payload["rolled_back"], payload["verified"]) == (
        "liquibase_rollback",
        2,
        True,
    )
    result = json.loads((attempt / "rollback.json").read_text(encoding="utf-8"))
    checks = [(c["check"], c["passed"]) for c in result["checks"]]
    assert ("check_absent", True) in checks
    assert ("check_present", True) in checks
    assert _check_names(target) == before
    code, payload = forge(
        capsys, "reconcile", "--model", str(base_model), "--changelog", str(base_changelog)
    )
    assert (code, payload["discrepancies"]) == (0, [])


def test_dropped_table_rollback_restores_check_and_identity(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    base = trail / "base"
    base.mkdir()
    write_operation(base, subject=BASE_STAMP)
    base_model = write_model(base / "model.yaml", EVENT)
    base_changelog = _generate_and_apply(
        capsys, base, base / "tasks.md", base_model, trail / "none"
    )
    before = _check_names(target)
    write_operation(trail, subject=STAMP, verdicts=("failure", "null", "null"), allow_drop=True)
    attempt = trail / "attempt-1"
    attempt.mkdir()
    model = write_model(attempt / "model.yaml", "  - name: task" + EVENT.split("  - name: task")[1])
    _generate_and_apply(capsys, attempt, trail / "tasks.md", model, base_model)

    use_case = rollback.build_use_case(accepted_master_path=str(trail / "accepted" / "master.yaml"))
    code = rollback.run(Namespace(operation=str(trail / "tasks.md"), attempt=1), use_case)
    payload = json.loads(capsys.readouterr().out)

    assert code == 0, payload
    assert _check_names(target) == before
    assert _identity(target, "event", "id") == "d"
    code, payload = forge(
        capsys, "reconcile", "--model", str(base_model), "--changelog", str(base_changelog)
    )
    assert (code, payload["discrepancies"]) == (0, [])


def test_cycle_with_identity_and_check_succeeds_and_rolls_back(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    model, changelog = _apply_event(capsys, trail)
    code, payload = forge(capsys, "reconcile", "--model", str(model), "--changelog", str(changelog))
    assert (code, payload["verdict"]) == (0, "success")
    write_operation(trail, subject=STAMP, verdicts=("failure", "null", "null"))

    use_case = rollback.build_use_case(accepted_master_path=str(trail / "accepted" / "master.yaml"))
    code = rollback.run(Namespace(operation=str(trail / "tasks.md"), attempt=1), use_case)
    payload = json.loads(capsys.readouterr().out)

    assert (code, payload["verified"]) == (0, True), payload
    assert _check_names(target) == set()
