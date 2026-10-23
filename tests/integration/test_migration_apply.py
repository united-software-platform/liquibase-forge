"""Накат changelog через раннер на `lbfr-db-test`: типы PostgreSQL, NOT NULL, порядок ключа."""

from __future__ import annotations

import shutil
from pathlib import Path

import psycopg
import pytest

from tests.conftest import TestDatabase
from tests.integration.migration_support import forge

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("runner_configured")]

EXAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "model" / "example.yaml"

EXPECTED_TYPES = {
    ("customer", "id"): ("uuid", True),
    ("customer", "email"): ("character varying(255)", True),
    ("customer", "full_name"): ("text", False),
    ("customer", "created_at"): ("timestamp with time zone", True),
    ("invoice_line", "invoice_id"): ("bigint", True),
    ("invoice_line", "line_no"): ("integer", True),
    ("invoice_line", "amount"): ("numeric(12,2)", True),
    ("invoice_line", "is_paid"): ("boolean", False),
    ("invoice_line", "due_date"): ("date", False),
    ("invoice_line", "created_at"): ("timestamp without time zone", False),
    ("invoice_line", "customer_id"): ("uuid", False),
}


def _generate(capsys: pytest.CaptureFixture[str], trail: Path, accepted: Path) -> tuple[int, str]:
    model = trail / "attempt-1" / "model.yaml"
    model.parent.mkdir(exist_ok=True)
    shutil.copyfile(EXAMPLE, model)
    changelog = trail / "attempt-1" / "changelog.yaml"
    code, _ = forge(
        capsys,
        "generate",
        "--model", str(model),
        "--accepted", str(accepted),
        "--operation", str(trail / "tasks.md"),
        "--out", str(changelog),
    )  # fmt: skip
    return code, str(changelog)


def test_apply_creates_columns_with_mapped_types(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    code, changelog = _generate(capsys, trail, trail / "missing.yaml")
    assert code == 0

    code, payload = forge(capsys, "apply", "--changelog", changelog)

    assert code == 0, payload
    assert (trail / "attempt-1" / "apply.json").exists()
    with psycopg.connect(target.conninfo) as connection:
        columns = connection.execute(
            "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull "
            "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname IN ('customer', 'invoice_line') "
            "AND a.attnum > 0 AND NOT a.attisdropped"
        ).fetchall()
        key = connection.execute(
            "SELECT array_agg(a.attname ORDER BY k.ordinality) "
            "FROM pg_constraint con "
            "CROSS JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ordinality) "
            "JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum "
            "WHERE con.conname = 'pk_invoice_line' AND con.contype = 'p'"
        ).fetchone()
        journal = connection.execute(
            "SELECT id, filename FROM databasechangelog ORDER BY orderexecuted"
        ).fetchall()

    assert {(t, c): (kind, notnull) for t, c, kind, notnull in columns} == EXPECTED_TYPES
    assert key == (["invoice_id", "line_no"],)
    assert journal == [
        ("20261017-153000-01", "db/changelog/20261017-153000.yaml"),
        ("20261017-153000-02", "db/changelog/20261017-153000.yaml"),
        ("20261017-153000-03", "db/changelog/20261017-153000.yaml"),
        ("20261017-153000-04", "db/changelog/20261017-153000.yaml"),
    ]


def test_empty_changelog_is_applied(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    code, changelog = _generate(capsys, trail, EXAMPLE)
    assert code == 0

    code, payload = forge(capsys, "apply", "--changelog", changelog)

    assert code == 0, payload


def test_liquibase_error_is_code_1_with_result(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    code, changelog = _generate(capsys, trail, trail / "missing.yaml")
    assert code == 0
    with psycopg.connect(target.conninfo) as connection:
        connection.execute("CREATE TABLE customer (id integer)")

    code, payload = forge(capsys, "apply", "--changelog", changelog)

    assert code == 1, payload
    assert (trail / "attempt-1" / "apply.json").exists()
