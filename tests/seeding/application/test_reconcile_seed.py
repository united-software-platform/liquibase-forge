"""Сценарий сверки seed: вердикт, результат, таблицы вне seed и ошибки входа и окружения."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.modeling.application.load_model.use_case import InvalidModelError
from forge.modeling.application.model_reading import ModelUnreadableError
from forge.reconciliation.application.contracts import ChangelogUnreadableError
from forge.seeding.application.accepted_seed import AcceptedSeedError
from forge.seeding.application.reconcile_seed.input import ReconcileSeedInput
from forge.seeding.application.reconcile_seed.use_case import SeedInvalidError
from forge.seeding.application.seed_reading import SeedUnreadableError
from forge.shared.application.settings import DatabaseUnavailableError
from forge.shared.domain.target_database import DatabaseNotAllowedError
from tests.migration.fakes import FakeSettings, FakeWriter
from tests.reconciliation.fakes import FakeChangesets
from tests.seeding.fakes import FakeDatabase, files, use_case

MATCHING = """version: 1
tables:
  - name: order_status
    rows:
      - {code: draft, title: Черновик}
      - {code: paid, title: Оплачен}
  - name: customer
    rows:
      - {id: 1}
"""


def _input(paths: dict[str, str]) -> ReconcileSeedInput:
    return ReconcileSeedInput(
        paths["seed"], paths["changelog"], paths["accepted_seed"], paths["model"]
    )


def test_success_writes_result_next_to_changelog(tmp_path: Path) -> None:
    writer = FakeWriter()
    db = FakeDatabase(MATCHING)

    output = use_case(tmp_path, db, writer).execute(_input(files(tmp_path)))

    assert (output.verdict, output.discrepancies) == ("success", ())
    result = str(tmp_path / "attempt-1" / "reconcile.json")
    assert output.result_path == result
    assert writer.documents[result] == {
        "seed": str(tmp_path / "attempt-1" / "seed.yaml"),
        "changelog": str(tmp_path / "attempt-1" / "changelog.yaml"),
        "database": "lbfr-db-test:5432/t_0001",
        "verdict": "success",
        "discrepancies": [],
    }


def test_tables_outside_seed_are_not_read(tmp_path: Path) -> None:
    db = FakeDatabase(MATCHING)

    use_case(tmp_path, db, FakeWriter()).execute(_input(files(tmp_path)))

    assert db.requested == ["order_status", "legacy_status"]


def test_missing_row_gives_failure_with_key(tmp_path: Path) -> None:
    writer = FakeWriter()
    rows = MATCHING.replace("      - {code: paid, title: Оплачен}\n", "")

    output = use_case(tmp_path, FakeDatabase(rows), writer).execute(_input(files(tmp_path)))

    assert output.verdict == "failure"
    (document,) = writer.documents.values()
    assert document["discrepancies"] == [
        {
            "kind": "row_missing",
            "table": "order_status",
            "key": {"code": "paid"},
            "column": None,
            "changeset": None,
            "expected": "present",
            "actual": "absent",
            "message": "строки order_status[code=paid] нет в БД",
        }
    ]


def test_removed_table_rows_and_journal_follow_seed_tables(tmp_path: Path) -> None:
    rows = MATCHING + "  - name: legacy_status\n    rows:\n      - {code: old}\n"

    output = use_case(tmp_path, FakeDatabase(rows, records=()), FakeWriter()).execute(
        _input(files(tmp_path))
    )

    assert [(d.kind, d.table, d.key, d.changeset) for d in output.discrepancies] == [
        ("row_unexpected", "legacy_status", (("code", "old"),), None),
        ("changeset_not_executed", None, None, "20261017-153000-01"),
    ]


def test_missing_accepted_seed_is_empty(tmp_path: Path) -> None:
    rows = MATCHING + "  - name: legacy_status\n    rows:\n      - {code: old}\n"
    db = FakeDatabase(rows)

    output = use_case(tmp_path, db, FakeWriter()).execute(_input(files(tmp_path, accepted=None)))

    assert (output.verdict, db.requested) == ("success", ["order_status"])


def test_repeated_reconciliation_gives_same_document(tmp_path: Path) -> None:
    rows = "version: 1\ntables:\n  - name: order_status\n    rows:\n      - {code: x, title: X}\n"
    first, second = FakeWriter(), FakeWriter()
    paths = files(tmp_path)

    use_case(tmp_path, FakeDatabase(rows), first).execute(_input(paths))
    use_case(tmp_path, FakeDatabase(rows), second).execute(_input(paths))

    assert first.documents == second.documents


def _fails(
    tmp_path: Path,
    error: type[Exception],
    paths: dict[str, str] | None = None,
    db: FakeDatabase | None = None,
    settings: FakeSettings | None = None,
    changesets: FakeChangesets | None = None,
) -> FakeDatabase:
    writer = FakeWriter()
    database = db or FakeDatabase(MATCHING)
    with pytest.raises(error):
        use_case(tmp_path, database, writer, settings, changesets).execute(
            _input(paths or files(tmp_path))
        )
    assert writer.documents == {}, "без вердикта reconcile.json не пишется"
    return database


def test_database_outside_allowlist_is_checked_before_connecting(tmp_path: Path) -> None:
    db = _fails(tmp_path, DatabaseNotAllowedError, settings=FakeSettings(allowlist="other:5432/x"))

    assert not db.connected


def test_unavailable_database(tmp_path: Path) -> None:
    _fails(tmp_path, DatabaseUnavailableError, db=FakeDatabase(MATCHING, available=False))


def test_invalid_attempt_seed_is_reported_before_connecting(tmp_path: Path) -> None:
    paths = files(tmp_path, seed="version: 1\ntables:\n  - name: unknown\n    rows: []\n")

    db = _fails(tmp_path, SeedInvalidError, paths)

    assert not db.connected


def test_unreadable_attempt_seed(tmp_path: Path) -> None:
    paths = files(tmp_path)
    (tmp_path / "attempt-1" / "seed.yaml").unlink()

    _fails(tmp_path, SeedUnreadableError, paths)


def test_invalid_accepted_seed(tmp_path: Path) -> None:
    accepted = "version: 1\ntables:\n  - name: unknown\n    rows: []\n"

    _fails(tmp_path, AcceptedSeedError, files(tmp_path, accepted=accepted))


def test_unreadable_model(tmp_path: Path) -> None:
    paths = files(tmp_path)
    (tmp_path / "model.yaml").unlink()

    _fails(tmp_path, ModelUnreadableError, paths)


def test_invalid_model(tmp_path: Path) -> None:
    paths = files(tmp_path)
    (tmp_path / "model.yaml").write_text("version: 1\ntables: 5\n", encoding="utf-8")

    _fails(tmp_path, InvalidModelError, paths)


def test_unreadable_changelog(tmp_path: Path) -> None:
    _fails(tmp_path, ChangelogUnreadableError, changesets=FakeChangesets(readable=False))
