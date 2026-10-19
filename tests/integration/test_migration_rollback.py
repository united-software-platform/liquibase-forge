"""Откат попытки через раннер на `lbfr-db-test`: полный, частичный и запасной путь."""

from __future__ import annotations

import json
import shutil
from argparse import Namespace
from pathlib import Path

import psycopg
import pytest

from forge.cli.commands import rollback
from tests.conftest import TestDatabase
from tests.integration.migration_support import STAMP, forge
from tests.migration.operation_backlog import write_operation

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("runner_configured")]

EXAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "model" / "example.yaml"
LOGICAL = f"db/changelog/{STAMP}.yaml"


def _apply_attempt(capsys: pytest.CaptureFixture[str], trail: Path) -> None:
    """Построить и накатить changelog модели-примера как попытку 1."""
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
    write_operation(trail, subject=STAMP, verdicts=("failure", "null", "null"))


def _state(database: TestDatabase) -> tuple[list[str], list[str]]:
    """Таблицы схемы `public` и `id` записей попытки в журнале."""
    with psycopg.connect(database.conninfo) as connection:
        tables = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        ).fetchall()
        journal = (
            connection.execute(
                "SELECT id FROM databasechangelog WHERE filename = %s ORDER BY orderexecuted",
                (LOGICAL,),
            ).fetchall()
            if ("databasechangelog",) in tables
            else []
        )
    return [t for (t,) in tables], [i for (i,) in journal]


def _rollback(capsys: pytest.CaptureFixture[str], trail: Path) -> tuple[int, dict[str, object]]:
    """Откатить попытку 1; принятый master — в следе, где его нет, а не в `db/` проекта."""
    use_case = rollback.build_use_case(accepted_master=str(trail / "accepted" / "master.yaml"))
    code = rollback.run(Namespace(operation=str(trail / "tasks.md"), attempt=1), use_case)
    return code, json.loads(capsys.readouterr().out)


def test_rollback_returns_schema(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    _apply_attempt(capsys, trail)
    assert _state(target)[1] == [f"{STAMP}-01", f"{STAMP}-02"]

    code, payload = _rollback(capsys, trail)

    assert code == 0, payload
    assert (payload["action"], payload["rolled_back"], payload["verified"]) == (
        "liquibase_rollback",
        2,
        True,
    )
    tables, journal = _state(target)
    assert "customer" not in tables and "invoice_line" not in tables and journal == []
    result = json.loads((trail / "attempt-1" / "rollback.json").read_text(encoding="utf-8"))
    assert result["verified"] is True


def test_partial_apply_rolls_back_applied_changesets(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    _apply_attempt(capsys, trail)
    # Состояние частичного наката: второй changeset не дошёл до журнала и схемы
    with psycopg.connect(target.conninfo) as connection:
        connection.execute("DELETE FROM databasechangelog WHERE id = %s", (f"{STAMP}-02",))
        connection.execute("DROP TABLE invoice_line")

    code, payload = _rollback(capsys, trail)

    assert code == 0, payload
    assert (payload["action"], payload["rolled_back"]) == ("liquibase_rollback", 1)
    assert _state(target)[1] == []


def test_foreign_entry_after_attempt_recreates_database(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    _apply_attempt(capsys, trail)
    with psycopg.connect(target.conninfo) as connection:
        connection.execute(
            "INSERT INTO databasechangelog (id, author, filename, dateexecuted, orderexecuted, "
            "exectype) VALUES ('foreign-01', 'someone', 'db/changelog/foreign.yaml', now(), 99, "
            "'EXECUTED')"
        )

    code, payload = _rollback(capsys, trail)

    assert code == 0, payload
    assert payload["action"] == "recreate_database"
    assert payload["fallback_reason"] == "записи попытки не являются хвостом журнала"
    assert _state(target) == ([], [])


def test_nothing_applied(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    write_operation(trail, subject=STAMP, verdicts=("failure", "null", "null"))

    code, payload = _rollback(capsys, trail)

    assert code == 0, payload
    assert (payload["action"], payload["verified"]) == ("none_applied", True)
