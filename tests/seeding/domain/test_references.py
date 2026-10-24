"""Ссылки внешних ключей между строками seed и циклы ссылок."""

from __future__ import annotations

import pytest

from forge.modeling.domain.draft import ColumnDraft
from forge.seeding.domain.draft import SeedDraft
from forge.seeding.domain.factory import SeedFactory
from forge.seeding.domain.seed import SeedViolationError
from forge.seeding.domain.seed_value import SeedValue
from tests.seeding.support import CATEGORY, CODE, i, model, reference, row, s, seed, table

STATUS_KIND = table("status_kind", CODE)
ORDER_STATUS = table(
    "order_status",
    CODE,
    ColumnDraft("kind_code", "string", length=32, nullable=False),
    ColumnDraft("customer_id", "bigint"),
    foreign_keys=(
        reference(("kind_code",), "status_kind", ("code",)),
        reference(("customer_id",), "customer", ("id",)),
    ),
)
CUSTOMER = table("customer", ColumnDraft("id", "bigint"), key=("id",))
MODEL = model(STATUS_KIND, ORDER_STATUS, CUSTOMER, CATEGORY)


def _violations(draft: SeedDraft) -> list[tuple[str, str]]:
    with pytest.raises(SeedViolationError) as error:
        SeedFactory().create(MODEL, draft)
    return [(v.path, v.code) for v in error.value.violations]


def _messages(draft: SeedDraft) -> list[str]:
    with pytest.raises(SeedViolationError) as error:
        SeedFactory().create(MODEL, draft)
    return [v.message for v in error.value.violations]


KINDS = ("status_kind", (row(code=s("final")), row(code=s("open"))))


def test_resolved_references() -> None:
    draft = seed(
        KINDS, ("order_status", (row(code=s("new"), kind_code=s("open")),)), ("customer", ())
    )

    result = SeedFactory().create(MODEL, draft)

    assert len(result.tables) == 3


def test_target_outside_seed_is_reported_once_per_foreign_key() -> None:
    rows = (
        row(code=s("new"), kind_code=s("open"), customer_id=i(1)),
        row(code=s("old"), kind_code=s("final")),
    )
    draft = seed(("order_status", rows), KINDS)

    assert _violations(draft) == [("tables[0].name", "unseeded_reference_table")]
    assert "customer" in _messages(draft)[0]


def test_target_excluded_by_structure_counts_as_seeded() -> None:
    draft = seed(
        KINDS,
        ("order_status", (row(code=s("new"), kind_code=s("open"), customer_id=i(7)),)),
        excluded=("customer",),
    )

    assert SeedFactory().create(MODEL, draft).tables[1].rows[0].values[1][1] == SeedValue("open")


def test_reference_to_missing_row() -> None:
    draft = seed(
        ("customer", ()),
        ("order_status", (row(code=s("new"), kind_code=s("archived")),)),
        KINDS,
    )

    assert _violations(draft) == [("tables[1].rows[0]", "unresolved_reference")]
    assert "code=archived" in _messages(draft)[0]


def test_unseeded_target_comes_before_unresolved_rows() -> None:
    draft = seed(KINDS, ("order_status", (row(code=s("new"), kind_code=s("closed")),)))

    assert _violations(draft) == [
        ("tables[1].name", "unseeded_reference_table"),
        ("tables[1].rows[0]", "unresolved_reference"),
    ]


def test_null_in_foreign_key_is_not_checked() -> None:
    draft = seed(("category", (row(code=s("root")),)))

    assert SeedFactory().create(MODEL, draft).tables[0].rows[0].values[1][1].is_null()


def test_broken_foreign_key_value_is_not_checked_again() -> None:
    draft = seed(("category", (row(code=s("root"), parent_code=i(1)),)))

    assert _violations(draft) == [("tables[0].rows[0].parent_code", "invalid_value")]


def test_self_reference_of_root_row_is_not_a_cycle() -> None:
    rows = (row(code=s("root"), parent_code=s("root")), row(code=s("shoes"), parent_code=s("root")))

    assert len(SeedFactory().create(MODEL, seed(("category", rows))).tables[0].rows) == 2


def test_cycle_of_two_rows() -> None:
    rows = (
        row(code=s("root"), parent_code=s("root")),
        row(code=s("a"), parent_code=s("b")),
        row(code=s("b"), parent_code=s("a")),
    )
    draft = seed(("category", rows))

    assert _violations(draft) == [("tables[0].rows[1]", "reference_cycle")]
    assert "category[code=a] → category[code=b] → category[code=a]" in _messages(draft)[0]


def test_cycle_is_reported_on_first_row_of_component() -> None:
    rows = (
        row(code=s("c"), parent_code=s("a")),
        row(code=s("a"), parent_code=s("b")),
        row(code=s("b"), parent_code=s("c")),
        row(code=s("x"), parent_code=s("y")),
        row(code=s("y"), parent_code=s("x")),
    )

    assert _violations(seed(("category", rows))) == [
        ("tables[0].rows[0]", "reference_cycle"),
        ("tables[0].rows[3]", "reference_cycle"),
    ]


def test_long_chain_without_cycle() -> None:
    chain = (row(code=s(f"n{n}"), parent_code=s(f"n{n - 1}")) for n in range(1, 3000))
    rows = (row(code=s("n0"), parent_code=s("n0")), *chain)

    assert len(SeedFactory().create(MODEL, seed(("category", rows))).tables[0].rows) == 3000


def test_long_cycle() -> None:
    rows = tuple(row(code=s(f"n{n}"), parent_code=s(f"n{(n + 1) % 3000}")) for n in range(3000))

    assert _violations(seed(("category", rows))) == [("tables[0].rows[0]", "reference_cycle")]
