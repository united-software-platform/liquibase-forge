"""Сверка seed на `lbfr-db-test`: все десять типов без расхождений и виды расхождений строк."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tests.conftest import TestDatabase
from tests.integration.migration_support import forge, write_model
from tests.migration.operation_backlog import write_operation

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("runner_configured")]

FIRST, SECOND = "20261025-101500", "20261026-090000"

TABLES = """
  - name: status
    columns:
      - {name: code, type: string, length: 32}
      - {name: title, type: text, nullable: false}
    primary_key: [code]
  - name: transition
    columns:
      - {name: code, type: string, length: 32}
      - {name: status_code, type: string, length: 32, nullable: false}
    primary_key: [code]
    foreign_keys:
      - columns: [status_code]
        references: {table: status, columns: [code]}
  - name: sample
    columns:
      - {name: code, type: string, length: 32}
      - {name: small, type: integer}
      - {name: big, type: bigint}
      - {name: flag, type: boolean}
      - {name: note, type: text}
      - {name: amount, type: decimal, precision: 12, scale: 2}
      - {name: starts_on, type: date}
      - {name: created_at, type: timestamp}
      - {name: valid_from, type: timestamp_tz}
      - {name: external_id, type: uuid}
    primary_key: [code]
  - name: customer
    columns:
      - {name: id, type: bigint}
    primary_key: [id]
"""

FIRST_SEED = """version: 1
tables:
  - name: status
    rows:
      - {code: open, title: Открыт}
      - {code: archived, title: Архив}
  - name: transition
    rows:
      - {code: t1, status_code: archived}
  - name: sample
    rows:
      - code: full
        small: -2147483648
        big: 9223372036854775807
        flag: true
        note: "O'Reilly"
        amount: "-12.50"
        starts_on: 2026-02-28
        created_at: "2026-03-01T10:20:30.120000"
        valid_from: "2026-03-01T10:20:30.5+03:00"
        external_id: "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
"""

# Таблица `transition` убрана из seed: changelog данных удаляет её строки
SECOND_SEED = FIRST_SEED.replace(
    "  - name: transition\n    rows:\n      - {code: t1, status_code: archived}\n", ""
)


def _model_operation(capsys: pytest.CaptureFixture[str], trail: Path) -> Path:
    directory = trail / "attempt-1"
    directory.mkdir()
    model = write_model(directory / "model.yaml", TABLES)
    code, payload = forge(
        capsys,
        "generate",
        "--model", str(model),
        "--accepted", str(trail / "missing.yaml"),
        "--operation", str(trail / "tasks.md"),
        "--out", str(directory / "changelog.yaml"),
    )  # fmt: skip
    assert code == 0, payload
    code, payload = forge(capsys, "apply", "--changelog", str(directory / "changelog.yaml"))
    assert code == 0, payload
    return directory


def _seed_operation(
    capsys: pytest.CaptureFixture[str], trail: Path, stamp: str, seed: str, accepted: Path
) -> Path:
    operation = trail / f"seed-{stamp}"
    directory = operation / "attempt-1"
    directory.mkdir(parents=True)
    shutil.copyfile(trail / "attempt-1" / "model.yaml", directory / "model.yaml")
    (directory / "seed.yaml").write_text(seed, encoding="utf-8")
    write_operation(operation, subject=stamp, mode="interactive")
    code, payload = forge(
        capsys,
        "generate-seed",
        "--seed", str(directory / "seed.yaml"),
        "--accepted-seed", str(accepted),
        "--model", str(directory / "model.yaml"),
        "--operation", str(operation / "tasks.md"),
        "--out", str(directory / "changelog.yaml"),
    )  # fmt: skip
    assert code == 0, payload
    code, payload = forge(capsys, "apply", "--changelog", str(directory / "changelog.yaml"))
    assert code == 0, payload
    return directory


def _reconcile_seed(
    capsys: pytest.CaptureFixture[str], directory: Path, accepted: Path
) -> tuple[int, dict[str, Any]]:
    return forge(
        capsys,
        "reconcile-seed",
        "--seed", str(directory / "seed.yaml"),
        "--changelog", str(directory / "changelog.yaml"),
        "--accepted-seed", str(accepted),
        "--model", str(directory / "model.yaml"),
    )  # fmt: skip


def _execute(database: TestDatabase, *statements: str) -> None:
    with psycopg.connect(database.conninfo) as connection:
        for statement in statements:
            connection.execute(statement)


def test_every_type_reconciles_without_discrepancies(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    _model_operation(capsys, trail)
    first = _seed_operation(capsys, trail, FIRST, FIRST_SEED, trail / "missing-seed.yaml")
    _execute(target, "INSERT INTO customer (id) VALUES (1)")

    code, payload = _reconcile_seed(capsys, first, trail / "missing-seed.yaml")

    assert code == 0, payload
    assert (payload["verdict"], payload["discrepancies"]) == ("success", [])
    result = json.loads((first / "reconcile.json").read_text(encoding="utf-8"))
    assert result == payload


def test_corrupted_extra_and_deleted_rows(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    _model_operation(capsys, trail)
    first = _seed_operation(capsys, trail, FIRST, FIRST_SEED, trail / "missing-seed.yaml")
    _execute(
        target,
        "UPDATE status SET title = 'Испорчен' WHERE code = 'open'",
        "INSERT INTO status (code, title) VALUES ('extra', 'Лишний')",
        "DELETE FROM transition WHERE code = 't1'",
        "UPDATE sample SET amount = 1.50 WHERE code = 'full'",
    )

    code, payload = _reconcile_seed(capsys, first, trail / "missing-seed.yaml")

    assert (code, payload["verdict"]) == (1, "failure"), payload
    found = [
        (d["kind"], d["table"], d["key"], d["column"], d["expected"], d["actual"])
        for d in payload["discrepancies"]
    ]
    assert found == [
        ("value_mismatch", "status", {"code": "open"}, "title", "Открыт", "Испорчен"),
        (
            "row_unexpected",
            "status",
            {"code": "extra"},
            None,
            "absent",
            "[code=extra, title=Лишний]",
        ),
        ("row_missing", "transition", {"code": "t1"}, None, "present", "absent"),
        ("value_mismatch", "sample", {"code": "full"}, "amount", "-12.5", "1.5"),
    ]


def test_removed_table_with_remaining_row(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    _model_operation(capsys, trail)
    first = _seed_operation(capsys, trail, FIRST, FIRST_SEED, trail / "missing-seed.yaml")
    second = _seed_operation(capsys, trail, SECOND, SECOND_SEED, first / "seed.yaml")

    code, payload = _reconcile_seed(capsys, second, first / "seed.yaml")
    assert (code, payload["discrepancies"]) == (0, []), payload

    _execute(target, "INSERT INTO transition (code, status_code) VALUES ('t9', 'open')")

    code, payload = _reconcile_seed(capsys, second, first / "seed.yaml")

    assert code == 1, payload
    assert [(d["kind"], d["table"], d["key"]) for d in payload["discrepancies"]] == [
        ("row_unexpected", "transition", {"code": "t9"}),
    ]
