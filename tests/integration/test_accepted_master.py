"""Принятый `master.yaml` двух операций накатывается Liquibase в порядке принятия."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from forge.operation.infrastructure.accepted_state import FileAcceptedState
from tests.conftest import TestDatabase
from tests.integration.migration_support import forge, write_model
from tests.migration.models import CUSTOMER, INVOICE
from tests.migration.operation_backlog import write_operation

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("runner_configured")]

FIRST, SECOND = "20261017-153000", "20261018-090000"


def _attempt(
    capsys: pytest.CaptureFixture[str], trail: Path, stamp: str, tables: str, accepted: Path
) -> Path:
    """Каталог попытки операции `stamp` с моделью и changelog от `accepted`."""
    operation = trail / stamp
    directory = operation / "attempt-1"
    directory.mkdir(parents=True)
    write_operation(operation, subject=stamp)
    model = write_model(directory / "model.yaml", tables)
    code, payload = forge(
        capsys,
        "generate",
        "--model", str(model),
        "--accepted", str(accepted),
        "--operation", str(operation / "tasks.md"),
        "--out", str(directory / "changelog.yaml"),
    )  # fmt: skip
    assert code == 0, payload
    return directory


def test_master_applies_operations_in_order(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    state = FileAcceptedState(trail / "db")
    first = _attempt(capsys, trail, FIRST, CUSTOMER, trail / "db" / "model.yaml")
    state.accept(FIRST, str(first))
    second = _attempt(capsys, trail, SECOND, CUSTOMER + INVOICE, trail / "db" / "model.yaml")
    files = state.accept(SECOND, str(second))

    code, payload = forge(capsys, "apply", "--changelog", files.master)

    assert code == 0, payload
    with psycopg.connect(target.conninfo) as connection:
        journal = connection.execute(
            "SELECT id, filename FROM databasechangelog ORDER BY orderexecuted"
        ).fetchall()
    assert journal == [
        (f"{FIRST}-01", f"db/changelog/{FIRST}.yaml"),
        (f"{SECOND}-01", f"db/changelog/{SECOND}.yaml"),
    ]
