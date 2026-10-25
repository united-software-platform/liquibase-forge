"""Чтение результатов попытки: сверка, откат, отсутствующие и нечитаемые файлы."""

from __future__ import annotations

import json
from pathlib import Path

from forge.migration.domain.changelog import Changelog
from forge.migration.domain.model_diff import ModelDiff
from forge.migration.domain.stamp import OperationStamp
from forge.migration.infrastructure.liquibase_changelog import render_changelog
from forge.operation.application.accepted_state import (
    DataChanges,
    DeletedRow,
    DestructiveChange,
    TableRowCounts,
)
from forge.operation.infrastructure.attempt_results import JsonAttemptResultsReader
from tests.migration.models import CUSTOMER, INVOICE, model
from tests.seeding.support import MIGRATION_EXAMPLE

PHONE = CUSTOMER.replace(
    "    primary_key", "      - {name: phone, type: text, nullable: false}\n    primary_key"
)


def test_reconcile_and_rollback(tmp_path: Path) -> None:
    (tmp_path / "reconcile.json").write_text(
        json.dumps(
            {
                "verdict": "failure",
                "discrepancies": [
                    {
                        "kind": "column_missing",
                        "table": "customer",
                        "column": "email",
                        "changeset": None,
                        "expected": "string(255)",
                        "actual": "absent",
                        "message": "колонки customer.email нет в БД",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "rollback.json").write_text(
        json.dumps({"action": "liquibase_rollback", "rolled_back": 2, "verified": True}),
        encoding="utf-8",
    )
    reader = JsonAttemptResultsReader()

    reconcile = reader.reconcile(str(tmp_path))
    rollback = reader.rollback(str(tmp_path))

    assert reconcile is not None and reconcile.verdict == "failure"
    assert reconcile.discrepancies[0].column == "email"
    assert rollback is not None
    assert (rollback.action, rollback.rolled_back, rollback.verified) == (
        "liquibase_rollback",
        2,
        True,
    )


def test_missing_files(tmp_path: Path) -> None:
    reader = JsonAttemptResultsReader()

    assert reader.reconcile(str(tmp_path)) is None
    assert reader.rollback(str(tmp_path / "attempt-9")) is None


def test_broken_file_counts_as_missing(tmp_path: Path) -> None:
    (tmp_path / "rollback.json").write_text("{не json", encoding="utf-8")

    assert JsonAttemptResultsReader().rollback(str(tmp_path)) is None


def _changelog(directory: Path, text: str) -> str:
    path = directory / "changelog.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_destructive_matches_rendered_changelog(tmp_path: Path) -> None:
    changes = ModelDiff().between(model(PHONE + INVOICE), model(CUSTOMER))
    path = _changelog(
        tmp_path, render_changelog(Changelog(OperationStamp("20261017-153000"), changes))
    )

    assert JsonAttemptResultsReader().destructive(path) == (
        DestructiveChange("invoice", None),
        DestructiveChange("customer", "phone"),
    )


def test_destructive_skips_additions_and_rollback_blocks(tmp_path: Path) -> None:
    changes = ModelDiff().between(model(CUSTOMER), model(PHONE + INVOICE))
    path = _changelog(
        tmp_path, render_changelog(Changelog(OperationStamp("20261017-153000"), changes))
    )

    assert JsonAttemptResultsReader().destructive(path) == ()


def test_destructive_skips_constraint_drops(tmp_path: Path) -> None:
    linked = CUSTOMER + "    unique:\n      - [email]\n"
    changes = ModelDiff().between(model(linked), model(CUSTOMER))
    path = _changelog(
        tmp_path, render_changelog(Changelog(OperationStamp("20261017-153000"), changes))
    )

    assert JsonAttemptResultsReader().destructive(path) == ()


def test_destructive_of_missing_or_foreign_file_is_empty(tmp_path: Path) -> None:
    reader = JsonAttemptResultsReader()

    assert reader.destructive(str(tmp_path / "missing.yaml")) == ()
    assert reader.destructive(_changelog(tmp_path, "databaseChangeLog: [{changeSet: {}}]\n")) == ()


def test_data_changes_of_data_changelog() -> None:
    changes = JsonAttemptResultsReader().data_changes(str(MIGRATION_EXAMPLE / "changelog.yaml"))

    assert changes.tables == (
        TableRowCounts("status_group", inserted=1, updated=0, deleted=0),
        TableRowCounts("order_status", inserted=2, updated=1, deleted=1),
    )
    assert changes.deleted == (DeletedRow("order_status", (("code", "archived"),)),)


def test_deleted_row_key_spans_composite_primary_key(tmp_path: Path) -> None:
    path = tmp_path / "changelog.yaml"
    path.write_text(
        "databaseChangeLog:\n"
        "- changeSet:\n"
        "    changes:\n"
        "    - delete:\n"
        "        tableName: price\n"
        "        where: \"region = 'north AND south'::TEXT AND since = NULL\"\n",
        encoding="utf-8",
    )

    changes = JsonAttemptResultsReader().data_changes(str(path))

    assert changes.deleted == (
        DeletedRow("price", (("region", "north AND south"), ("since", None))),
    )


def test_data_changes_of_missing_or_model_changelog_are_empty(tmp_path: Path) -> None:
    reader = JsonAttemptResultsReader()
    model = tmp_path / "model.yaml"
    model.write_text(
        "databaseChangeLog:\n- changeSet:\n    changes:\n"
        "    - createTable:\n        tableName: x\n",
        encoding="utf-8",
    )

    assert reader.data_changes(str(tmp_path / "missing.yaml")) == DataChanges((), ())
    assert reader.data_changes(str(model)) == DataChanges((), ())
