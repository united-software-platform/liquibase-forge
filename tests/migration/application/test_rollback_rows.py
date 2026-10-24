"""Проверка возврата строк changelog данных: сценарии дельты `forge-migration`."""

from __future__ import annotations

from forge.migration.application.changelog_storage import ChangelogSummary, RowRef
from forge.migration.application.rollback_attempt.input import RollbackAttemptInput
from forge.migration.application.rollback_attempt.output import RollbackAttemptOutput
from forge.migration.application.rollback_attempt.use_case import (
    RollbackAttemptUseCase,
    RollbackDependencies,
)
from tests.migration.fakes import (
    LOGICAL,
    SUMMARY,
    FakeDatabase,
    FakeOperations,
    FakeSettings,
    FakeWriter,
)

PAID = RowRef("order_status", "code = 'paid'::VARCHAR(32)")
DRAFT = RowRef("order_status", "code = 'draft'::VARCHAR(32)", (("title", "'Черновик'::TEXT"),))
ARCHIVED = RowRef(
    "order_status",
    "code = 'archived'::VARCHAR(32)",
    (("code", "'archived'::VARCHAR(32)"), ("title", "'Архив'::TEXT")),
)
DATA_SUMMARY = ChangelogSummary(
    LOGICAL,
    SUMMARY.changeset_ids,
    (),
    (),
    inserted_rows=(PAID,),
    updated_rows=(DRAFT,),
    deleted_rows=(ARCHIVED,),
)
RESTORED = {DRAFT: 1, ARCHIVED: 1}


def _rollback(db: FakeDatabase) -> tuple[RollbackAttemptOutput, FakeWriter]:
    writer = FakeWriter()
    use_case = RollbackAttemptUseCase(
        RollbackDependencies(
            operations=FakeOperations("failure"),
            settings=FakeSettings(),
            changelogs=db,
            journal=db,
            schema=db,
            rows=db,
            recreator=db,
            gateway=db,
            writer=writer,
        ),
        "db/changelog/master.yaml",
    )
    return use_case.execute(RollbackAttemptInput("trail/tasks.md", 1)), writer


def _checks(writer: FakeWriter) -> list[tuple[str, bool]]:
    document = writer.documents["trail/attempt-1/rollback.json"]
    return [(c["check"], c["passed"]) for c in document["checks"]]


def test_inserted_row_is_absent_after_rollback() -> None:
    db = FakeDatabase(summary=DATA_SUMMARY, row_counts=dict(RESTORED))
    db.apply_attempt(3)

    output, writer = _rollback(db)

    assert (output.action, output.verified) == ("liquibase_rollback", True)
    assert _checks(writer) == [
        ("journal_clean", True),
        ("row_absent", True),
        ("row_restored", True),
        ("row_present", True),
    ]
    document = writer.documents["trail/attempt-1/rollback.json"]
    assert document["checks"][1]["detail"] == (
        "строка order_status WHERE code = 'paid'::VARCHAR(32): найдено 0"
    )


def test_update_not_rolled_back_fails_row_restored() -> None:
    db = FakeDatabase(summary=DATA_SUMMARY, row_counts={ARCHIVED: 1})
    db.apply_attempt(3)

    output, writer = _rollback(db)

    assert output.verified is False
    assert ("row_restored", False) in _checks(writer)
    restored = next(c for c in output.checks if c.check == "row_restored")
    assert "title = 'Черновик'::TEXT" in restored.detail


def test_inserted_row_left_fails_row_absent() -> None:
    db = FakeDatabase(summary=DATA_SUMMARY, row_counts={**RESTORED, PAID: 1})
    db.apply_attempt(3)

    output, _ = _rollback(db)

    assert output.verified is False
    assert [c.passed for c in output.checks if c.check == "row_absent"] == [False]


def test_fallback_for_data_restores_master_and_checks_rows() -> None:
    db = FakeDatabase(
        summary=DATA_SUMMARY, row_counts=dict(RESTORED), rollback_code=1, master_exists=True
    )
    db.apply_attempt(3)

    output, writer = _rollback(db)

    assert db.calls == ["rollback 3", "recreate", "update db/changelog/master.yaml"]
    assert (output.action, output.verified) == ("recreate_database", True)
    assert _checks(writer) == [
        ("accepted_restored", True),
        ("journal_clean", True),
        ("row_absent", True),
        ("row_restored", True),
        ("row_present", True),
    ]


def test_model_changelog_gets_no_row_checks() -> None:
    db = FakeDatabase()
    db.apply_attempt(3)

    output, _ = _rollback(db)

    assert not [c for c in output.checks if c.check.startswith("row_")]
