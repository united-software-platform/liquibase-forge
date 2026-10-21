"""Сценарий сверки: вердикты, `reconcile.json` и ошибки окружения без файла."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.modeling.application.load_model.use_case import InvalidModelError, LoadModelUseCase
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader
from forge.reconciliation.application.contracts import ChangelogUnreadableError
from forge.reconciliation.application.reconcile.input import ReconcileInput
from forge.reconciliation.application.reconcile.output import ReconcileOutput
from forge.reconciliation.application.reconcile.use_case import (
    ReconcileDependencies,
    ReconcileUseCase,
)
from forge.shared.application.settings import DatabaseUnavailableError
from forge.shared.domain.target_database import DatabaseNotAllowedError
from tests.migration.fakes import FakeSettings, FakeWriter
from tests.migration.models import CUSTOMER
from tests.reconciliation.fakes import EXECUTED, FakeChangesets, FakeReconcileDatabase
from tests.reconciliation.schemas import customer, schema


def _reconcile(
    tmp_path: Path,
    db: FakeReconcileDatabase,
    writer: FakeWriter,
    tables: str = CUSTOMER,
    allowlist: str = "lbfr-db-test:5432/*",
    changesets: FakeChangesets | None = None,
) -> ReconcileOutput:
    model = tmp_path / "model.yaml"
    model.write_text("version: 1\ntables:\n" + tables, encoding="utf-8")
    use_case = ReconcileUseCase(
        ReconcileDependencies(
            settings=FakeSettings(allowlist),
            models=LoadModelUseCase(YamlModelDraftReader(), DataModelFactory()),
            changesets=changesets or FakeChangesets(),
            schema=db,
            journal=db,
            writer=writer,
        )
    )
    return use_case.execute(ReconcileInput(str(model), "trail/attempt-1/changelog.yaml"))


def test_success(tmp_path: Path) -> None:
    writer = FakeWriter()

    output = _reconcile(tmp_path, FakeReconcileDatabase(schema(customer()), EXECUTED), writer)

    assert (output.verdict, output.discrepancies) == ("success", ())
    assert output.result_path == "trail/attempt-1/reconcile.json"
    document = writer.documents["trail/attempt-1/reconcile.json"]
    assert (document["verdict"], document["discrepancies"], document["database"]) == (
        "success",
        [],
        "lbfr-db-test:5432/t_0001",
    )


def test_failure_lists_schema_and_journal_discrepancies(tmp_path: Path) -> None:
    writer = FakeWriter()

    output = _reconcile(tmp_path, FakeReconcileDatabase(schema(customer(key=None))), writer)

    assert output.verdict == "failure"
    assert [d.kind for d in output.discrepancies] == [
        "primary_key_mismatch",
        "changeset_not_executed",
    ]
    assert len(writer.documents["trail/attempt-1/reconcile.json"]["discrepancies"]) == 2


def test_database_outside_allowlist_is_not_connected(tmp_path: Path) -> None:
    db, writer = FakeReconcileDatabase(schema(customer()), EXECUTED), FakeWriter()

    with pytest.raises(DatabaseNotAllowedError):
        _reconcile(tmp_path, db, writer, allowlist="lbfr-db:5432/forge")

    assert not db.connected and writer.documents == {}


def test_unavailable_database_leaves_no_result(tmp_path: Path) -> None:
    writer = FakeWriter()

    with pytest.raises(DatabaseUnavailableError):
        _reconcile(tmp_path, FakeReconcileDatabase(schema(), available=False), writer)

    assert writer.documents == {}


def test_invalid_model_leaves_no_result(tmp_path: Path) -> None:
    writer = FakeWriter()

    with pytest.raises(InvalidModelError):
        _reconcile(
            tmp_path,
            FakeReconcileDatabase(schema(customer())),
            writer,
            CUSTOMER.replace("uuid", "varchar"),
        )

    assert writer.documents == {}


def test_unreadable_changelog_leaves_no_result(tmp_path: Path) -> None:
    writer = FakeWriter()

    with pytest.raises(ChangelogUnreadableError):
        _reconcile(
            tmp_path,
            FakeReconcileDatabase(schema(customer())),
            writer,
            changesets=FakeChangesets(False),
        )

    assert writer.documents == {}
