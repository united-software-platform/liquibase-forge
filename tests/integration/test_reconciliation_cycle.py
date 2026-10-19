"""Сквозная сверка через раннер на `lbfr-db-test`: накат модели-примера и виды расхождений."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import psycopg
import pytest

from tests.conftest import TestDatabase
from tests.integration.migration_support import STAMP, forge

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("runner_configured")]

EXAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "model" / "example.yaml"


def _apply_example(capsys: pytest.CaptureFixture[str], trail: Path) -> tuple[str, str]:
    """Построить и накатить changelog модели-примера со всеми десятью типами."""
    model = trail / "attempt-1" / "model.yaml"
    model.parent.mkdir()
    shutil.copyfile(EXAMPLE, model)
    changelog = trail / "attempt-1" / "changelog.yaml"
    code, _ = forge(
        capsys,
        "generate",
        "--model", str(model),
        "--accepted", str(trail / "missing.yaml"),
        "--operation", str(trail / "tasks.md"),
        "--out", str(changelog),
    )  # fmt: skip
    assert code == 0
    code, payload = forge(capsys, "apply", "--changelog", str(changelog))
    assert code == 0, payload
    return str(model), str(changelog)


def test_applied_model_reconciles_without_discrepancies(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    model, changelog = _apply_example(capsys, trail)

    code, payload = forge(capsys, "reconcile", "--model", model, "--changelog", changelog)

    assert code == 0, payload
    assert (payload["verdict"], payload["discrepancies"]) == ("success", [])
    result = json.loads((trail / "attempt-1" / "reconcile.json").read_text(encoding="utf-8"))
    assert result == payload


DRIFTS: list[tuple[str, str, tuple[str | None, str | None, str | None]]] = [
    (
        "ALTER TABLE customer ADD COLUMN legacy text",
        "column_unexpected",
        ("customer", "legacy", None),
    ),
    (
        "ALTER TABLE customer ALTER COLUMN email TYPE varchar(320)",
        "column_type_mismatch",
        ("customer", "email", None),
    ),
    (
        "ALTER TABLE customer ALTER COLUMN created_at DROP NOT NULL",
        "column_nullable_mismatch",
        ("customer", "created_at", None),
    ),
    (
        f"DELETE FROM databasechangelog WHERE id = '{STAMP}-02'",
        "changeset_not_executed",
        (None, None, f"{STAMP}-02"),
    ),
    (
        f"UPDATE databasechangelog SET exectype = 'MARK_RAN' WHERE id = '{STAMP}-01'",
        "changeset_not_executed",
        (None, None, f"{STAMP}-01"),
    ),
]


@pytest.mark.parametrize(("statement", "kind", "subject"), DRIFTS)
def test_drift_gives_discrepancy(
    capsys: pytest.CaptureFixture[str],
    trail: Path,
    target: TestDatabase,
    statement: str,
    kind: str,
    subject: tuple[str | None, str | None, str | None],
) -> None:
    model, changelog = _apply_example(capsys, trail)
    with psycopg.connect(target.conninfo) as connection:
        connection.execute(statement)

    code, payload = forge(capsys, "reconcile", "--model", model, "--changelog", changelog)

    assert code == 1, payload
    found = [
        (d["kind"], (d["table"], d["column"], d["changeset"])) for d in payload["discrepancies"]
    ]
    assert found == [(kind, subject)]
