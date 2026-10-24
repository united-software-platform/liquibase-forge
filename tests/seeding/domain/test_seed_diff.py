"""Разница seed: вставки, изменения и удаления по PK, порядок, группировка и конфликты unique."""

from __future__ import annotations

import pytest

from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.draft import ColumnDraft
from forge.modeling.domain.identifier import ColumnName
from forge.seeding.domain.draft import RawValue, RowDraft, SeedDraft
from forge.seeding.domain.factory import SeedFactory
from forge.seeding.domain.row_changes import (
    RowChangeKind,
    RowDelete,
    RowGroup,
    RowUpdate,
    UnsupportedRowChangeError,
    row_label,
)
from forge.seeding.domain.seed import Seed
from forge.seeding.domain.seed_diff import SeedDiff
from forge.seeding.domain.seed_value import SeedValue
from tests.seeding.support import (
    CATEGORY,
    CODE,
    NULL,
    ORDER_STATUS,
    i,
    model,
    reference,
    row,
    s,
    seed,
    table,
)

LEGACY_STATUS = table("legacy_status", CODE)
PRICE = table("price", CODE, ColumnDraft("fee", "decimal", precision=12, scale=2, nullable=False))
MODEL = model(ORDER_STATUS, LEGACY_STATUS, PRICE, CATEGORY)


def _seed(draft: SeedDraft, data_model: DataModel = MODEL) -> Seed:
    return SeedFactory().create(data_model, draft)


def _diff(
    accepted: SeedDraft, attempt: SeedDraft, data_model: DataModel = MODEL
) -> tuple[RowGroup, ...]:
    return SeedDiff().between(_seed(accepted, data_model), _seed(attempt, data_model))


def _plan(groups: tuple[RowGroup, ...]) -> list[tuple[str, str, list[str]]]:
    """Группы как «вид, таблица, строки по PK» для сравнения."""
    return [
        (
            group.kind.value,
            group.table.name.value,
            [
                row_label(
                    change.table, change.after if isinstance(change, RowUpdate) else change.row
                )
                for change in group.changes
            ],
        )
        for group in groups
    ]


def _status(code: str, title: str, **values: RawValue) -> RowDraft:
    return row(code=s(code), title=s(title), **values)


def test_new_row_is_insert() -> None:
    accepted = seed(("order_status", (_status("draft", "Черновик"),)))
    attempt = seed(("order_status", (_status("draft", "Черновик"), _status("paid", "Оплачен"))))

    assert _plan(_diff(accepted, attempt)) == [
        ("insert", "order_status", ["order_status[code=paid]"])
    ]


def test_changed_value_is_update_of_that_column_only() -> None:
    accepted = seed(("order_status", (_status("draft", "Черновик", description=s("x")),)))
    attempt = seed(("order_status", (_status("draft", "Набросок", description=s("x")),)))

    (group,) = _diff(accepted, attempt)

    (change,) = group.changes
    assert isinstance(change, RowUpdate)
    assert group.kind is RowChangeKind.UPDATE
    assert change.changed() == (ColumnName("title"),)
    assert change.before.value(ColumnName("title")) == SeedValue("Черновик")
    assert change.after.value(ColumnName("title")) == SeedValue("Набросок")


def test_same_value_in_different_notation_is_no_change() -> None:
    accepted = seed(("price", (row(code=s("base"), fee=s("1.50")),)))
    attempt = seed(("price", (row(code=s("base"), fee=s("1.5")),)))

    assert _diff(accepted, attempt) == ()


def test_equal_seeds_give_no_changes() -> None:
    draft = seed(("order_status", (_status("draft", "Черновик"),)), ("legacy_status", ()))

    assert _diff(draft, draft) == ()


def test_removed_row_is_delete_with_accepted_values() -> None:
    accepted = seed(("order_status", (_status("draft", "Черновик"), _status("archived", "Архив"))))
    attempt = seed(("order_status", (_status("draft", "Черновик"),)))

    (group,) = _diff(accepted, attempt)

    (change,) = group.changes
    assert isinstance(change, RowDelete)
    assert change.row.value(ColumnName("title")) == SeedValue("Архив")


def test_table_removed_from_seed_is_cleared() -> None:
    accepted = seed(
        ("order_status", (_status("draft", "Черновик"),)),
        ("legacy_status", (row(code=s("old")), row(code=s("older")))),
    )
    attempt = seed(("order_status", (_status("draft", "Черновик"),)))

    assert _plan(_diff(accepted, attempt)) == [
        ("delete", "legacy_status", ["legacy_status[code=old]", "legacy_status[code=older]"])
    ]


def test_first_fill_inserts_every_row() -> None:
    attempt = seed(
        ("order_status", (_status("draft", "Черновик"),)),
        ("legacy_status", (row(code=s("old")),)),
    )

    assert _plan(_diff(seed(), attempt)) == [
        ("insert", "order_status", ["order_status[code=draft]"]),
        ("insert", "legacy_status", ["legacy_status[code=old]"]),
    ]


# Порядок и группировка

STATUS = table("status", CODE)
TRANSITION = table(
    "transition",
    CODE,
    ColumnDraft("status_code", "string", length=32, nullable=False),
    foreign_keys=(reference(("status_code",), "status", ("code",)),),
)
WORKFLOW = model(STATUS, TRANSITION)


def test_references_are_moved_before_target_row_is_removed() -> None:
    accepted = seed(
        ("status", (row(code=s("open")), row(code=s("archived")))),
        ("transition", (row(code=s("t1"), status_code=s("archived")),)),
    )
    attempt = seed(
        ("status", (row(code=s("open")), row(code=s("closed")))),
        ("transition", (row(code=s("t1"), status_code=s("closed")),)),
    )

    assert _plan(_diff(accepted, attempt, WORKFLOW)) == [
        ("insert", "status", ["status[code=closed]"]),
        ("update", "transition", ["transition[code=t1]"]),
        ("delete", "status", ["status[code=archived]"]),
    ]


def test_dependent_rows_are_inserted_after_targets_and_deleted_before() -> None:
    attempt = seed(("status", (row(code=s("open")),)), ("transition", ()))
    accepted = seed(
        ("transition", (row(code=s("t1"), status_code=s("open")),)),
        ("status", (row(code=s("open")),)),
    )

    assert _plan(_diff(accepted, attempt, WORKFLOW)) == [
        ("delete", "transition", ["transition[code=t1]"]),
    ]
    assert _plan(_diff(seed(), accepted, WORKFLOW)) == [
        ("insert", "status", ["status[code=open]"]),
        ("insert", "transition", ["transition[code=t1]"]),
    ]


CATEGORY_MODEL = model(CATEGORY)
TREE = seed(
    (
        "category",
        (
            row(code=s("boots"), parent_code=s("shoes")),
            row(code=s("shoes"), parent_code=s("root")),
            row(code=s("root"), parent_code=s("root")),
            row(code=s("hats"), parent_code=NULL),
        ),
    )
)


def test_tree_inside_one_table_is_inserted_from_parents() -> None:
    assert _plan(_diff(seed(), TREE, CATEGORY_MODEL)) == [
        (
            "insert",
            "category",
            [
                "category[code=root]",
                "category[code=shoes]",
                "category[code=boots]",
                "category[code=hats]",
            ],
        )
    ]


def test_tree_inside_one_table_is_deleted_from_children() -> None:
    assert _plan(_diff(TREE, seed(("category", ())), CATEGORY_MODEL)) == [
        (
            "delete",
            "category",
            [
                "category[code=boots]",
                "category[code=shoes]",
                "category[code=root]",
                "category[code=hats]",
            ],
        )
    ]


def test_reference_table_without_references_is_one_changeset() -> None:
    rows = tuple(row(code=s(f"s{n}")) for n in range(5))

    (group,) = _diff(seed(), seed(("legacy_status", rows)))

    assert (group.kind, len(group.changes)) == (RowChangeKind.INSERT, 5)


ALPHA = table(
    "alpha",
    CODE,
    ColumnDraft("beta_code", "string", length=32),
    foreign_keys=(reference(("beta_code",), "beta", ("code",)),),
)
BETA = table(
    "beta",
    CODE,
    ColumnDraft("alpha_code", "string", length=32),
    foreign_keys=(reference(("alpha_code",), "alpha", ("code",)),),
)
CYCLIC_TABLES = model(ALPHA, BETA)
CYCLIC_SEED = seed(
    ("alpha", (row(code=s("a1"), beta_code=s("b1")),)),
    ("beta", (row(code=s("b1")), row(code=s("b2"), alpha_code=s("a1")))),
)


def test_table_cycle_without_row_cycle_splits_table_into_changesets() -> None:
    assert _plan(_diff(seed(), CYCLIC_SEED, CYCLIC_TABLES)) == [
        ("insert", "beta", ["beta[code=b1]"]),
        ("insert", "alpha", ["alpha[code=a1]"]),
        ("insert", "beta", ["beta[code=b2]"]),
    ]
    assert _plan(_diff(CYCLIC_SEED, seed(("alpha", ()), ("beta", ())), CYCLIC_TABLES)) == [
        ("delete", "beta", ["beta[code=b2]"]),
        ("delete", "alpha", ["alpha[code=a1]"]),
        ("delete", "beta", ["beta[code=b1]"]),
    ]


def test_updates_follow_attempt_seed_order() -> None:
    accepted = seed(
        ("legacy_status", (row(code=s("a")),)),
        ("order_status", (_status("b", "Б"), _status("a", "А"))),
    )
    attempt = seed(
        ("order_status", (_status("a", "А2"), _status("b", "Б2"))),
        ("legacy_status", (row(code=s("a")),)),
    )

    assert _plan(_diff(accepted, attempt)) == [
        ("update", "order_status", ["order_status[code=a]", "order_status[code=b]"])
    ]


# Конфликты уникальности


def test_swap_of_unique_values_is_unsupported() -> None:
    accepted = seed(("order_status", (_status("draft", "Черновик"), _status("new", "Новый"))))
    attempt = seed(("order_status", (_status("draft", "Новый"), _status("new", "Черновик"))))

    with pytest.raises(UnsupportedRowChangeError) as error:
        _diff(accepted, attempt)

    (conflict,) = error.value.changes
    assert (conflict.code, conflict.table, conflict.columns) == (
        "unique_conflict",
        "order_status",
        ("title",),
    )
    assert set(conflict.rows) == {"order_status[code=draft]", "order_status[code=new]"}


def test_reuse_of_deleted_row_value_is_unsupported() -> None:
    accepted = seed(("order_status", (_status("archived", "Архив"),)))
    attempt = seed(("order_status", (_status("closed", "Архив"),)))

    with pytest.raises(UnsupportedRowChangeError) as error:
        _diff(accepted, attempt)

    (conflict,) = error.value.changes
    assert conflict.rows == ("order_status[code=closed]", "order_status[code=archived]")
    assert "удаляется" in conflict.message


def test_kept_unique_value_and_null_values_are_not_conflicts() -> None:
    accepted = seed(
        (
            "order_status",
            (
                _status("draft", "Черновик", description=s("x")),
                _status("old", "Старый", external_code=NULL),
            ),
        )
    )
    attempt = seed(
        (
            "order_status",
            (
                _status("draft", "Черновик", description=s("y")),
                _status("new", "Новый", external_code=NULL),
            ),
        )
    )

    assert _plan(_diff(accepted, attempt)) == [
        ("insert", "order_status", ["order_status[code=new]"]),
        ("update", "order_status", ["order_status[code=draft]"]),
        ("delete", "order_status", ["order_status[code=old]"]),
    ]


def test_integer_keys_are_compared_by_value() -> None:
    numbered = model(table("level", ColumnDraft("id", "integer"), key=("id",)))

    groups = _diff(
        seed(("level", (row(id=i(1)),))), seed(("level", (row(id=i(1)), row(id=i(2))))), numbered
    )

    assert _plan(groups) == [("insert", "level", ["level[id=2]"])]


# Изменение ключа-набора, на который ведут ссылки

STATUS_BY_TITLE = table(
    "status",
    CODE,
    ColumnDraft("title", "text", nullable=False),
    ColumnDraft("alias", "string", length=16),
    ColumnDraft("note", "text"),
    unique=(("title",), ("alias",)),
)
TRANSITION_BY_TITLE = table(
    "transition",
    CODE,
    ColumnDraft("status_title", "text"),
    ColumnDraft("status_alias", "string", length=16),
    foreign_keys=(
        reference(("status_title",), "status", ("title",)),
        reference(("status_alias",), "status", ("alias",)),
    ),
)
BY_TITLE = model(STATUS_BY_TITLE, TRANSITION_BY_TITLE)
SLUGS = model(
    table(
        "node",
        CODE,
        ColumnDraft("slug", "string", length=16, nullable=False),
        ColumnDraft("parent_slug", "string", length=16),
        unique=(("slug",),),
        foreign_keys=(reference(("parent_slug",), "node", ("slug",)),),
    )
)


def _key_changes(
    accepted: SeedDraft, attempt: SeedDraft, data_model: DataModel = BY_TITLE
) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    with pytest.raises(UnsupportedRowChangeError) as error:
        _diff(accepted, attempt, data_model)
    return [(c.code, c.columns, c.rows) for c in error.value.changes]


def test_change_of_referenced_old_value_is_unsupported() -> None:
    accepted = seed(
        ("status", (row(code=s("open"), title=s("Открыт")),)),
        ("transition", (row(code=s("t1"), status_title=s("Открыт")),)),
    )
    attempt = seed(
        ("status", (row(code=s("open"), title=s("Открыт заказ")),)),
        ("transition", (row(code=s("t1"), status_title=s("Открыт заказ")),)),
    )

    assert _key_changes(accepted, attempt) == [
        ("referenced_key_changed", ("title",), ("status[code=open]", "transition[code=t1]"))
    ]


def test_insert_referencing_new_value_is_unsupported() -> None:
    accepted = seed(("status", (row(code=s("open"), title=s("Открыт")),)), ("transition", ()))
    attempt = seed(
        ("status", (row(code=s("open"), title=s("Закрыт")),)),
        ("transition", (row(code=s("t2"), status_title=s("Закрыт")),)),
    )

    assert _key_changes(accepted, attempt) == [
        ("referenced_key_changed", ("title",), ("status[code=open]", "transition[code=t2]"))
    ]


def test_reference_by_primary_key_is_not_rejected() -> None:
    accepted = seed(
        ("status", (row(code=s("open")),)),
        ("transition", (row(code=s("t1"), status_code=s("open")),)),
    )
    attempt = seed(
        ("status", (row(code=s("open")),)),
        ("transition", (row(code=s("t1"), status_code=s("open")),)),
    )
    status_title = model(
        table("status", CODE, ColumnDraft("title", "text"), unique=(("title",),)),
        TRANSITION,
    )
    renamed = seed(
        ("status", (row(code=s("open"), title=s("Новое")),)),
        ("transition", (row(code=s("t1"), status_code=s("open")),)),
    )

    assert _diff(accepted, attempt, status_title) == ()
    assert _plan(_diff(accepted, renamed, status_title)) == [
        ("update", "status", ["status[code=open]"])
    ]


def test_unreferenced_key_change_and_other_columns_are_not_rejected() -> None:
    accepted = seed(
        ("status", (row(code=s("open"), title=s("Открыт")), row(code=s("done"), title=s("Готов")))),
        ("transition", (row(code=s("t1"), status_title=s("Открыт")),)),
    )
    attempt = seed(
        (
            "status",
            (
                row(code=s("open"), title=s("Открыт"), note=s("заметка")),
                row(code=s("done"), title=s("Выполнен")),
            ),
        ),
        ("transition", (row(code=s("t1"), status_title=s("Открыт")),)),
    )

    assert _plan(_diff(accepted, attempt, BY_TITLE)) == [
        ("update", "status", ["status[code=open]", "status[code=done]"])
    ]


def test_null_key_values_are_not_references() -> None:
    accepted = seed(
        ("status", (row(code=s("open"), title=s("Открыт")),)),
        ("transition", (row(code=s("t1"), status_title=NULL),)),
    )
    attempt = seed(
        ("status", (row(code=s("open"), title=s("Открыт"), alias=s("o")),)),
        ("transition", (row(code=s("t1"), status_title=NULL, status_alias=NULL),)),
    )

    assert _plan(_diff(accepted, attempt, BY_TITLE)) == [
        ("update", "status", ["status[code=open]"])
    ]


def test_self_reference_through_changed_key_is_not_rejected() -> None:
    accepted = seed(("node", (row(code=s("root"), slug=s("a"), parent_slug=s("a")),)))
    attempt = seed(("node", (row(code=s("root"), slug=s("b"), parent_slug=s("b")),)))

    assert _plan(_diff(accepted, attempt, SLUGS)) == [("update", "node", ["node[code=root]"])]
