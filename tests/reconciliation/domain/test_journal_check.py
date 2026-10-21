"""Проверка журнала Liquibase: исполненные, отсутствующие и помеченные changeset."""

from __future__ import annotations

from forge.reconciliation.domain.journal_check import (
    ExpectedChangeSet,
    JournalCheck,
    JournalRecord,
)

FILE = "db/changelog/20261017-153000.yaml"
EXPECTED = (
    ExpectedChangeSet("20261017-153000-01", "forge", FILE),
    ExpectedChangeSet("20261017-153000-02", "forge", FILE),
)


def _found(*records: JournalRecord) -> list[tuple[str | None, str]]:
    return [(d.changeset, d.actual) for d in JournalCheck().compare(EXPECTED, records)]


def test_all_executed() -> None:
    assert (
        _found(
            JournalRecord("20261017-153000-01", "forge", FILE, "EXECUTED"),
            JournalRecord("20261017-153000-02", "forge", FILE, "EXECUTED"),
        )
        == []
    )


def test_missing_changeset() -> None:
    assert _found(JournalRecord("20261017-153000-01", "forge", FILE, "EXECUTED")) == [
        ("20261017-153000-02", "absent")
    ]


def test_mark_ran_is_not_executed() -> None:
    discrepancies = JournalCheck().compare(
        EXPECTED[:1], [JournalRecord("20261017-153000-01", "forge", FILE, "MARK_RAN")]
    )

    (found,) = discrepancies
    assert (found.kind, found.expected, found.actual) == (
        "changeset_not_executed",
        "EXECUTED",
        "MARK_RAN",
    )


def test_record_of_other_file_does_not_count() -> None:
    assert _found(
        JournalRecord("20261017-153000-01", "forge", "db/changelog/other.yaml", "EXECUTED"),
        JournalRecord("20261017-153000-02", "forge", FILE, "EXECUTED"),
    ) == [("20261017-153000-01", "absent")]


def test_empty_changelog() -> None:
    assert JournalCheck().compare((), ()) == ()
