"""Сценарий отката: каждая ветка схемы из design.md на подставной БД."""

from __future__ import annotations

import pytest

from forge.migration.application.database import JournalEntry
from forge.migration.application.liquibase_gateway import GatewayResult, GatewayUnavailableError
from forge.migration.application.rollback_attempt.input import RollbackAttemptInput
from forge.migration.application.rollback_attempt.output import RollbackAttemptOutput
from forge.migration.application.rollback_attempt.use_case import (
    RollbackAttemptUseCase,
    RollbackDependencies,
)
from forge.migration.domain.target_database import DatabaseNotAllowedError, TargetDatabase
from tests.migration.fakes import (
    LOGICAL,
    FakeDatabase,
    FakeOperations,
    FakeSettings,
    FakeWriter,
)


def _rollback(
    db: FakeDatabase, verdict: str | None = "failure", allowlist: str = "lbfr-db-test:5432/*"
) -> tuple[RollbackAttemptOutput, FakeWriter]:
    writer = FakeWriter()
    use_case = RollbackAttemptUseCase(
        RollbackDependencies(
            operations=FakeOperations(verdict),
            settings=FakeSettings(allowlist),
            changelogs=db,
            journal=db,
            schema=db,
            recreator=db,
            gateway=db,
            writer=writer,
        )
    )
    return use_case.execute(RollbackAttemptInput("trail/tasks.md", 1)), writer


def test_success_verdict_changes_nothing() -> None:
    db = FakeDatabase()
    db.apply_attempt(3)

    output, writer = _rollback(db, verdict="success")

    assert (output.action, output.verified, output.result_path) == ("none", True, None)
    assert db.calls == [] and writer.documents == {}


@pytest.mark.parametrize("verdict", ["failure", None])
def test_full_rollback_through_liquibase(verdict: str | None) -> None:
    db = FakeDatabase()
    db.apply_attempt(3)

    output, writer = _rollback(db, verdict=verdict)

    assert db.calls == ["rollback 3"]
    assert (output.action, output.rolled_back, output.verified) == ("liquibase_rollback", 3, True)
    document = writer.documents["trail/attempt-1/rollback.json"]
    assert document["verified"] is True
    assert {c["check"] for c in document["checks"]} == {
        "journal_clean",
        "table_absent",
        "column_absent",
    }


def test_partial_apply_rolls_back_only_applied_changesets() -> None:
    db = FakeDatabase()
    db.apply_attempt(2)

    output, _ = _rollback(db)

    assert db.calls == ["rollback 2"]
    assert (output.rolled_back, output.verified) == (2, True)


def test_nothing_applied_does_not_call_liquibase() -> None:
    db = FakeDatabase()
    db.apply_attempt(0)

    output, writer = _rollback(db)

    assert db.calls == []
    assert (output.action, output.verified) == ("none_applied", True)
    assert "trail/attempt-1/rollback.json" in writer.documents


def test_foreign_entry_after_attempt_takes_fallback() -> None:
    db = FakeDatabase(master_exists=True)
    db.apply_attempt(2)
    db.journal.append(JournalEntry("other-01", "forge", "db/changelog/other.yaml", 9))

    output, _ = _rollback(db)

    assert db.calls == ["recreate", "update db/changelog/master.yaml"]
    assert output.action == "recreate_database"
    assert output.fallback_reason == "записи попытки не являются хвостом журнала"
    assert output.verified is True


def test_liquibase_failure_takes_fallback() -> None:
    db = FakeDatabase(rollback_code=1)
    db.apply_attempt(3)

    output, _ = _rollback(db)

    assert db.calls == ["rollback 3", "recreate"]
    assert (output.action, output.fallback_reason) == (
        "recreate_database",
        "откат Liquibase завершился ошибкой",
    )
    assert output.verified is True
    assert output.checks[0].check == "accepted_restored"


def test_missing_changelog_takes_fallback_and_checks_only_journal() -> None:
    db = FakeDatabase(summary=None)
    db.apply_attempt(1)

    output, _ = _rollback(db)

    assert db.calls == ["recreate"]
    assert output.fallback_reason == "changelog попытки не найден"
    assert [c.check for c in output.checks] == [
        "accepted_restored",
        "journal_clean",
        "attempt_objects",
    ]


def test_unknown_changeset_in_journal_takes_fallback() -> None:
    db = FakeDatabase()
    db.apply_attempt(1)
    db.journal[-1] = JournalEntry("20261017-153000-09", "forge", LOGICAL, 2)

    output, _ = _rollback(db)

    assert output.action == "recreate_database"
    assert "20261017-153000-09" in (output.fallback_reason or "")


def test_unconfirmed_return_is_reported() -> None:
    db = FakeDatabase()
    db.apply_attempt(3)
    db.rollback = lambda changelog, database, count: GatewayResult("req", 0, "", "")  # type: ignore[method-assign]

    output, writer = _rollback(db)

    assert output.verified is False
    failed = [c.check for c in output.checks if not c.passed]
    assert failed == ["journal_clean", "table_absent", "table_absent", "column_absent"]
    assert writer.documents["trail/attempt-1/rollback.json"]["verified"] is False


def test_database_outside_allowlist_is_refused_before_any_change() -> None:
    db = FakeDatabase()
    db.apply_attempt(3)

    with pytest.raises(DatabaseNotAllowedError):
        _rollback(db, allowlist="lbfr-db:5432/forge")

    assert db.calls == []


def test_unavailable_gateway_propagates() -> None:
    db = FakeDatabase()
    db.apply_attempt(3)

    def unavailable(changelog: str, database: TargetDatabase, count: int) -> GatewayResult:
        raise GatewayUnavailableError("runner_unavailable", "раннер недоступен")

    db.rollback = unavailable  # type: ignore[method-assign]

    with pytest.raises(GatewayUnavailableError):
        _rollback(db)
