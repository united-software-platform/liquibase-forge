"""Чтение результатов попытки: сверка, откат, отсутствующие и нечитаемые файлы."""

from __future__ import annotations

import json
from pathlib import Path

from forge.operation.infrastructure.attempt_results import JsonAttemptResultsReader


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
