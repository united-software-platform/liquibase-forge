"""Сравнение фактических строк таблиц seed с seed попытки."""

from __future__ import annotations

from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.draft import ColumnDraft
from forge.modeling.domain.identifier import TableName
from forge.reconciliation.domain.discrepancy import Discrepancy
from forge.seeding.domain.draft import RowDraft
from forge.seeding.domain.factory import SeedFactory
from forge.seeding.domain.rows_comparison import SeedRowsComparison
from forge.seeding.domain.seed import Seed, SeedRow
from tests.seeding.support import CODE, ORDER_STATUS, model, row, s, seed, table

LEGACY_STATUS = table("legacy_status", CODE)
SCHEDULE = table("schedule", CODE, ColumnDraft("valid_from", "timestamp_tz", nullable=False))
MODEL = model(ORDER_STATUS, LEGACY_STATUS, SCHEDULE)

DRAFT = row(code=s("draft"), title=s("Черновик"))
PAID = row(code=s("paid"), title=s("Оплачен"))
LEGACY = row(code=s("legacy"), title=s("Устаревший"), description=s("старый"))


def _seed(*tables: tuple[str, tuple[RowDraft, ...]], data_model: DataModel = MODEL) -> Seed:
    return SeedFactory().create(data_model, seed(*tables))


def _rows(name: str, *rows: RowDraft) -> tuple[SeedRow, ...]:
    """Фактические строки таблицы в нормализованной форме, как их вернёт чтение из БД."""
    return _seed((name, rows)).table(TableName(name)).rows


def _compare(
    attempt: Seed, actual: dict[str, tuple[SeedRow, ...]], removed: tuple[str, ...] = ()
) -> tuple[Discrepancy, ...]:
    return SeedRowsComparison().compare(
        attempt,
        tuple(MODEL.table(TableName(name)) for name in removed),
        {TableName(name): rows for name, rows in actual.items()},
    )


def test_matching_rows_give_no_discrepancies() -> None:
    attempt = _seed(("order_status", (DRAFT, PAID)))

    assert _compare(attempt, {"order_status": _rows("order_status", DRAFT, PAID)}) == ()


def test_same_moment_in_different_notation_is_equal() -> None:
    attempt = _seed(("schedule", (row(code=s("a"), valid_from=s("2026-01-01T03:00:00+03:00")),)))
    actual = _rows("schedule", row(code=s("a"), valid_from=s("2026-01-01T00:00:00Z")))

    assert _compare(attempt, {"schedule": actual}) == ()


def test_missing_row() -> None:
    attempt = _seed(("order_status", (DRAFT, PAID)))

    (found,) = _compare(attempt, {"order_status": _rows("order_status", DRAFT)})

    assert found == Discrepancy(
        "row_missing",
        "order_status",
        None,
        None,
        "present",
        "absent",
        "строки order_status[code=paid] нет в БД",
        (("code", "paid"),),
    )


def test_unexpected_row_carries_actual_values() -> None:
    attempt = _seed(("order_status", (DRAFT,)))

    (found,) = _compare(attempt, {"order_status": _rows("order_status", DRAFT, LEGACY)})

    assert found == Discrepancy(
        "row_unexpected",
        "order_status",
        None,
        None,
        "absent",
        "[code=legacy, title=Устаревший, description=старый, external_code=null]",
        "лишняя строка order_status[code=legacy]: в seed попытки её нет",
        (("code", "legacy"),),
    )


def test_value_mismatch_per_column() -> None:
    attempt = _seed(("order_status", (DRAFT,)))
    actual = _rows("order_status", row(code=s("draft"), title=s("Набросок")))

    (found,) = _compare(attempt, {"order_status": actual})

    assert found == Discrepancy(
        "value_mismatch",
        "order_status",
        "title",
        None,
        "Черновик",
        "Набросок",
        "значение order_status[code=draft].title: ожидалось 'Черновик', в БД 'Набросок'",
        (("code", "draft"),),
    )


def test_missing_key_in_seed_expects_null() -> None:
    attempt = _seed(("order_status", (DRAFT,)))
    actual = _rows("order_status", row(code=s("draft"), title=s("Черновик"), description=s("x")))

    (found,) = _compare(attempt, {"order_status": actual})

    assert (found.kind, found.column, found.expected, found.actual) == (
        "value_mismatch",
        "description",
        "null",
        "x",
    )


def test_removed_table_must_be_empty() -> None:
    attempt = _seed(("order_status", (DRAFT,)))
    actual = {
        "order_status": _rows("order_status", DRAFT),
        "legacy_status": _rows("legacy_status", row(code=s("old"))),
    }

    (found,) = _compare(attempt, actual, removed=("legacy_status",))

    assert (found.kind, found.table, found.key) == (
        "row_unexpected",
        "legacy_status",
        (("code", "old"),),
    )
    assert "убрана из seed и должна быть пуста" in found.message


def test_order_follows_seed_then_unexpected_then_removed_tables() -> None:
    attempt = _seed(
        ("schedule", (row(code=s("a"), valid_from=s("2026-01-01T00:00:00Z")),)),
        ("order_status", (PAID, DRAFT)),
    )
    actual = {
        "order_status": _rows(
            "order_status",
            row(code=s("draft"), title=s("Набросок"), description=s("x")),
            LEGACY,
        ),
        "schedule": _rows("schedule", row(code=s("b"), valid_from=s("2026-01-01T00:00:00Z"))),
        "legacy_status": _rows("legacy_status", row(code=s("old"))),
    }

    found = _compare(attempt, actual, removed=("legacy_status",))

    assert [(d.kind, d.table, d.key, d.column) for d in found] == [
        ("row_missing", "schedule", (("code", "a"),), None),
        ("row_unexpected", "schedule", (("code", "b"),), None),
        ("row_missing", "order_status", (("code", "paid"),), None),
        ("value_mismatch", "order_status", (("code", "draft"),), "title"),
        ("value_mismatch", "order_status", (("code", "draft"),), "description"),
        ("row_unexpected", "order_status", (("code", "legacy"),), None),
        ("row_unexpected", "legacy_status", (("code", "old"),), None),
    ]
    assert _compare(attempt, actual, removed=("legacy_status",)) == found
