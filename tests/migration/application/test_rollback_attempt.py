"""Сценарий отката: каждая ветка схемы из design.md на подставной БД."""

from __future__ import annotations

import pytest

from forge.migration.application.changelog_storage import ChangelogSummary, ConstraintRef
from forge.migration.application.database import JournalEntry
from forge.migration.application.liquibase_gateway import GatewayResult, GatewayUnavailableError
from forge.migration.application.rollback_attempt.input import RollbackAttemptInput
from forge.migration.application.rollback_attempt.output import RollbackAttemptOutput
from forge.migration.application.rollback_attempt.use_case import (
    RollbackAttemptUseCase,
    RollbackDependencies,
)
from forge.shared.domain.target_database import DatabaseNotAllowedError, TargetDatabase
from tests.migration.fakes import (
    LOGICAL,
    FakeDatabase,
    FakeOperations,
    FakeSettings,
    FakeWriter,
)


def _rollback(
    db: FakeDatabase,
    verdict: str | None = "failure",
    allowlist: str = "lbfr-db-test:5432/*",
    discard: bool = False,
    **options: str,
) -> tuple[RollbackAttemptOutput, FakeWriter]:
    writer = FakeWriter()
    options.setdefault("accepted_master", "db/changelog/master.yaml")
    use_case = RollbackAttemptUseCase(
        RollbackDependencies(
            operations=FakeOperations(verdict),
            settings=FakeSettings(allowlist),
            changelogs=db,
            journal=db,
            schema=db,
            rows=db,
            recreator=db,
            gateway=db,
            writer=writer,
        ),
        **options,
    )
    return use_case.execute(RollbackAttemptInput("trail/tasks.md", 1, discard=discard)), writer


def test_success_verdict_changes_nothing() -> None:
    db = FakeDatabase()
    db.apply_attempt(3)

    output, writer = _rollback(db, verdict="success")

    assert (output.action, output.verified, output.result_path) == ("none", True, None)
    assert db.calls == [] and writer.documents == {}


def test_discard_rolls_back_success_verdict() -> None:
    db = FakeDatabase()
    db.apply_attempt(3)

    output, writer = _rollback(db, verdict="success", discard=True)

    assert db.calls == ["rollback 3"]
    assert (output.action, output.rolled_back, output.verified) == ("liquibase_rollback", 3, True)
    assert output.result_path == "trail/attempt-1/rollback.json"
    document = writer.documents["trail/attempt-1/rollback.json"]
    assert (document["verdict"], document["verified"]) == ("success", True)


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


def test_fallback_restores_given_accepted_master() -> None:
    db = FakeDatabase(master_exists=True)
    db.apply_attempt(2)
    db.journal.append(JournalEntry("other-01", "forge", "db/changelog/other.yaml", 9))

    output, _ = _rollback(db, accepted_master="trail/accepted/master.yaml")

    assert db.calls == ["recreate", "update trail/accepted/master.yaml"]
    assert output.checks[0].detail == "накат trail/accepted/master.yaml: код 0"


def test_fallback_restores_master_outside_db() -> None:
    db = FakeDatabase(master_exists=True)
    db.apply_attempt(2)
    db.journal.append(JournalEntry("other-01", "forge", "db/changelog/other.yaml", 9))

    _rollback(db, accepted_master=".forge/db/changelog/master.yaml")

    assert db.calls == ["recreate", "update .forge/db/changelog/master.yaml"]


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


DROP_SUMMARY = ChangelogSummary(
    LOGICAL,
    ("20261017-153000-01", "20261017-153000-02"),
    (),
    (),
    dropped_tables=("invoice_line",),
    dropped_columns=(("customer", "email"),),
)


def test_dropped_objects_not_restored_fail_return_check() -> None:
    db = FakeDatabase(summary=DROP_SUMMARY)
    db.apply_attempt(2)

    output, _ = _rollback(db)

    failed = {c.check for c in output.checks if not c.passed}
    assert failed == {"table_present", "column_present"}
    assert output.verified is False


def test_restored_dropped_objects_pass_return_check() -> None:
    db = FakeDatabase(summary=DROP_SUMMARY)
    db.apply_attempt(2)

    def restoring(changelog: str, database: TargetDatabase, count: int) -> GatewayResult:
        db.journal = db.journal[:-count]
        db.tables = {"customer", "invoice_line"}
        db.columns = {("customer", "id"), ("customer", "email")}
        return GatewayResult("req", 0, "", "")

    db.rollback = restoring  # type: ignore[method-assign]

    output, writer = _rollback(db)

    passed = {c.check for c in output.checks if c.passed}
    assert {"journal_clean", "table_present", "column_present"} <= passed
    assert output.verified is True
    assert writer.documents["trail/attempt-1/rollback.json"]["verified"] is True


ADDED_FK = ConstraintRef("foreign_key", "invoice", "fk_invoice_0a1b2c3d")
ADDED_UQ = ConstraintRef("unique", "customer", "uq_customer_4e5f6a7b")
DROPPED_FK = ConstraintRef("foreign_key", "payment", "fk_payment_8c9d0e1f")
DROPPED_UQ = ConstraintRef("unique", "customer", "uq_customer_2a3b4c5d")
CONSTRAINT_SUMMARY = ChangelogSummary(
    LOGICAL,
    ("20261017-153000-01", "20261017-153000-02", "20261017-153000-03", "20261017-153000-04"),
    (),
    (),
    constraints=(ADDED_UQ, ADDED_FK),
    dropped_constraints=(DROPPED_FK, DROPPED_UQ),
)


def test_constraint_checks_pass_after_return() -> None:
    db = FakeDatabase(summary=CONSTRAINT_SUMMARY)
    db.apply_attempt(2)

    def restoring(changelog: str, database: TargetDatabase, count: int) -> GatewayResult:
        db.journal = db.journal[:-count]
        db.constraints = {(c.kind, c.table, c.name) for c in CONSTRAINT_SUMMARY.dropped_constraints}
        return GatewayResult("req", 0, "", "")

    db.rollback = restoring  # type: ignore[method-assign]

    output, _ = _rollback(db)

    assert [(c.check, c.passed) for c in output.checks[1:]] == [
        ("unique_absent", True),
        ("foreign_key_absent", True),
        ("foreign_key_present", True),
        ("unique_present", True),
    ]
    assert "fk_invoice_0a1b2c3d" in output.checks[2].detail
    assert output.verified is True


def test_constraint_checks_fail_when_not_returned() -> None:
    db = FakeDatabase(summary=CONSTRAINT_SUMMARY)
    db.apply_attempt(2)

    def leaving(changelog: str, database: TargetDatabase, count: int) -> GatewayResult:
        db.journal = db.journal[:-count]
        db.constraints = {("foreign_key", "invoice", "fk_invoice_0a1b2c3d")}
        return GatewayResult("req", 0, "", "")

    db.rollback = leaving  # type: ignore[method-assign]

    output, _ = _rollback(db)

    failed = [c.check for c in output.checks if not c.passed]
    assert failed == ["foreign_key_absent", "foreign_key_present", "unique_present"]
    assert output.verified is False


ADDED_CK = ConstraintRef("check", "event", "ck_event_1a2b3c4d")
DROPPED_CK = ConstraintRef("check", "event", "ck_event_5e6f7a8b")
CHECK_SUMMARY = ChangelogSummary(
    LOGICAL,
    ("20261017-153000-01", "20261017-153000-02"),
    (),
    (),
    constraints=(ADDED_CK,),
    dropped_constraints=(DROPPED_CK,),
)


def test_check_constraints_are_verified_after_return() -> None:
    db = FakeDatabase(summary=CHECK_SUMMARY)
    db.apply_attempt(2)

    def restoring(changelog: str, database: TargetDatabase, count: int) -> GatewayResult:
        db.journal = db.journal[:-count]
        db.constraints = {("check", "event", "ck_event_5e6f7a8b")}
        return GatewayResult("req", 0, "", "")

    db.rollback = restoring  # type: ignore[method-assign]

    output, _ = _rollback(db)

    assert [(c.check, c.passed) for c in output.checks[1:]] == [
        ("check_absent", True),
        ("check_present", True),
    ]
    assert "перечень значений event.ck_event_1a2b3c4d" in output.checks[1].detail
    assert output.verified is True
