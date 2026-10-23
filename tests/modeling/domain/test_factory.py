"""Фабрика модели: сборка из черновика и все нарушения сразу с путями от корня файла."""

from __future__ import annotations

from dataclasses import replace

import pytest

from forge.modeling.domain.column_type import TypeKind
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.draft import ColumnDraft, DataModelDraft, ForeignKeyDraft, TableDraft
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.domain.identifier import ColumnName, TableName
from forge.modeling.domain.unique_set import UniqueSet
from forge.modeling.domain.violation import ModelViolationError
from tests.modeling.example import EXAMPLE


def _table(
    position: int, name: str, *columns: ColumnDraft, key: tuple[str, ...] = ("id",)
) -> TableDraft:
    return TableDraft(position, name, columns or (ColumnDraft("id", "bigint"),), key)


def _violations(*tables: TableDraft) -> list[tuple[str, str]]:
    with pytest.raises(ModelViolationError) as caught:
        DataModelFactory().create(DataModelDraft(tables))
    return [(v.path, v.code) for v in caught.value.violations]


def test_example_model_is_built() -> None:
    model = DataModelFactory().create(EXAMPLE)

    assert isinstance(model, DataModel)
    invoice_line = model.table(TableName("invoice_line"))
    assert [column.name.value for column in invoice_line.columns][:2] == ["invoice_id", "line_no"]
    assert invoice_line.primary_key.columns == (ColumnName("invoice_id"), ColumnName("line_no"))
    assert invoice_line.column(ColumnName("amount")).type.precision == 12
    assert invoice_line.is_nullable(ColumnName("line_no")) is False
    assert invoice_line.is_nullable(ColumnName("is_paid")) is True
    kinds = {column.type.kind for table in model.tables for column in table.columns}
    assert kinds == set(TypeKind)


def test_empty_draft_gives_empty_model() -> None:
    assert DataModelFactory().create(DataModelDraft(())).tables == ()


def test_violations_in_two_tables_are_reported_together() -> None:
    assert _violations(
        _table(0, "customer", ColumnDraft("id", "bigint"), ColumnDraft("email", "string")),
        _table(1, "invoice", ColumnDraft("id", "bigint"), key=("id", "code")),
    ) == [
        ("tables[0].columns[1].length", "missing_type_parameter"),
        ("tables[1].primary_key[1]", "primary_key_unknown_column"),
    ]


def test_column_name_and_type_violations_are_reported_together() -> None:
    assert _violations(
        _table(0, "customer", ColumnDraft("id", "bigint"), ColumnDraft("Email", "varchar"))
    ) == [
        ("tables[0].columns[1].name", "invalid_identifier"),
        ("tables[0].columns[1].type", "unknown_type"),
    ]


def test_table_invariants_are_checked_despite_invalid_table_name() -> None:
    assert _violations(
        _table(0, "order", ColumnDraft("id", "bigint"), ColumnDraft("id", "text"))
    ) == [
        ("tables[0].name", "reserved_identifier"),
        ("tables[0].columns[1].name", "duplicate_name"),
    ]


def test_table_invariants_wait_for_valid_columns() -> None:
    assert _violations(
        _table(0, "customer", ColumnDraft("id", "bigint"), ColumnDraft("xmin", "bigint")),
    ) == [("tables[0].columns[1].name", "reserved_identifier")]


def test_primary_key_with_invalid_name_is_unknown_column() -> None:
    assert _violations(_table(0, "customer", key=("id", "Code"))) == [
        ("tables[0].primary_key[1]", "primary_key_unknown_column")
    ]


def test_primary_key_violations_are_prefixed() -> None:
    assert _violations(_table(0, "customer", key=())) == [
        ("tables[0].primary_key", "empty_primary_key")
    ]
    assert _violations(_table(0, "customer", key=("id", "id"))) == [
        ("tables[0].primary_key[1]", "primary_key_duplicate_column")
    ]


def test_primary_key_nullable_path_is_from_root() -> None:
    assert _violations(_table(3, "customer", ColumnDraft("id", "bigint", nullable=True))) == [
        ("tables[3].columns[0].nullable", "primary_key_nullable")
    ]


def test_duplicate_table_name_comes_first_among_its_table_violations() -> None:
    assert _violations(
        _table(0, "customer"),
        _table(1, "customer", ColumnDraft("id", "string")),
        _table(2, "invoice", key=()),
    ) == [
        ("tables[1].name", "duplicate_name"),
        ("tables[1].columns[0].length", "missing_type_parameter"),
        ("tables[2].primary_key", "empty_primary_key"),
    ]


def test_duplicate_name_is_found_among_invalid_tables() -> None:
    assert _violations(
        _table(0, "customer", key=("code",)),
        _table(1, "customer", key=("code",)),
    ) == [
        ("tables[0].primary_key[0]", "primary_key_unknown_column"),
        ("tables[1].name", "duplicate_name"),
        ("tables[1].primary_key[0]", "primary_key_unknown_column"),
    ]


def test_positions_come_from_draft() -> None:
    # Таблица на позиции 0 исключена из черновика из-за структурных нарушений
    assert _violations(_table(1, "customer", key=("code",))) == [
        ("tables[1].primary_key[0]", "primary_key_unknown_column")
    ]


def test_violation_order_is_stable() -> None:
    draft = (
        _table(0, "Customer", ColumnDraft("id", "decimal")),
        _table(1, "invoice", ColumnDraft("id", "integer", length=3), key=("id", "id")),
    )

    assert _violations(*draft) == _violations(*draft)


def _fk(columns: tuple[str, ...], table: str, target: tuple[str, ...] = ("id",)) -> ForeignKeyDraft:
    return ForeignKeyDraft(columns, table, target)


def _related(
    position: int,
    name: str,
    *columns: ColumnDraft,
    key: tuple[str, ...] = ("id",),
    unique: tuple[tuple[str, ...], ...] = (),
    foreign_keys: tuple[ForeignKeyDraft, ...] = (),
) -> TableDraft:
    return TableDraft(
        position, name, columns or (ColumnDraft("id", "bigint"),), key, unique, foreign_keys
    )


CUSTOMER = _related(
    0,
    "customer",
    ColumnDraft("id", "bigint"),
    ColumnDraft("email", "string", length=255),
)


def _invoice(*keys: ForeignKeyDraft, position: int = 1) -> TableDraft:
    return _related(
        position,
        "invoice",
        ColumnDraft("id", "bigint"),
        ColumnDraft("customer_id", "bigint"),
        ColumnDraft("customer_email", "string", length=255),
        ColumnDraft("small_id", "integer"),
        foreign_keys=keys,
    )


def test_unique_set_is_built() -> None:
    model = DataModelFactory().create(
        DataModelDraft((_related(0, "customer", *CUSTOMER.columns, unique=(("email",),)),))
    )

    assert model.tables[0].unique == (UniqueSet((ColumnName("email"),)),)


@pytest.mark.parametrize(
    ("unique", "expected"),
    [
        ((("email", "phone"),), [("tables[0].unique[0][1]", "unique_unknown_column")]),
        ((("email", "Phone"),), [("tables[0].unique[0][1]", "unique_unknown_column")]),
        (((),), [("tables[0].unique[0]", "empty_unique")]),
        ((("email", "email"),), [("tables[0].unique[0][1]", "unique_duplicate_column")]),
        ((("id",),), [("tables[0].unique[0]", "unique_equals_primary_key")]),
        ((("id", "email"), ("email", "id")), [("tables[0].unique[1]", "unique_duplicate")]),
    ],
)
def test_unique_rules(unique: tuple[tuple[str, ...], ...], expected: list[tuple[str, str]]) -> None:
    assert _violations(_related(0, "customer", *CUSTOMER.columns, unique=unique)) == expected


def test_foreign_key_is_built() -> None:
    model = DataModelFactory().create(
        DataModelDraft((CUSTOMER, _invoice(_fk(("customer_id",), "customer"))))
    )

    (key,) = model.table(TableName("invoice")).foreign_keys
    assert (key.columns, key.target, key.target_columns) == (
        (ColumnName("customer_id"),),
        TableName("customer"),
        (ColumnName("id"),),
    )


def test_foreign_key_to_table_below_in_model() -> None:
    draft = DataModelDraft(
        (_invoice(_fk(("customer_id",), "customer"), position=0), replace(CUSTOMER, position=1))
    )

    assert DataModelFactory().create(draft).tables[0].foreign_keys


def test_self_reference_and_cycle_are_valid() -> None:
    category = _related(
        0,
        "category",
        ColumnDraft("id", "bigint"),
        ColumnDraft("parent_id", "bigint"),
        foreign_keys=(_fk(("parent_id",), "category"),),
    )
    a = _related(
        1,
        "a",
        ColumnDraft("id", "bigint"),
        ColumnDraft("b_id", "bigint"),
        foreign_keys=(_fk(("b_id",), "b"),),
    )
    b = _related(
        2,
        "b",
        ColumnDraft("id", "bigint"),
        ColumnDraft("a_id", "bigint"),
        foreign_keys=(_fk(("a_id",), "a"),),
    )

    model = DataModelFactory().create(DataModelDraft((category, a, b)))

    assert [len(table.foreign_keys) for table in model.tables] == [1, 1, 1]


def test_foreign_key_to_unique_set_and_composite_key_in_other_order() -> None:
    customer = replace(CUSTOMER, unique=(("email",),))
    line = _related(
        2,
        "invoice_line",
        ColumnDraft("invoice_id", "bigint"),
        ColumnDraft("line_no", "integer"),
        key=("invoice_id", "line_no"),
    )
    payment = _related(
        3,
        "payment",
        ColumnDraft("id", "bigint"),
        ColumnDraft("invoice_id", "bigint"),
        ColumnDraft("line_no", "integer"),
        foreign_keys=(_fk(("line_no", "invoice_id"), "invoice_line", ("line_no", "invoice_id")),),
    )
    invoice = _invoice(_fk(("customer_email",), "customer", ("email",)))

    DataModelFactory().create(DataModelDraft((customer, invoice, line, payment)))


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (
            _fk(("customer_id",), "client"),
            [("tables[1].foreign_keys[0].references.table", "foreign_key_unknown_table")],
        ),
        (
            _fk(("customer_id",), "Client"),
            [("tables[1].foreign_keys[0].references.table", "foreign_key_unknown_table")],
        ),
        (
            _fk(("client_id",), "customer"),
            [("tables[1].foreign_keys[0].columns[0]", "foreign_key_unknown_column")],
        ),
        (
            _fk(("customer_id",), "customer", ("uid",)),
            [
                (
                    "tables[1].foreign_keys[0].references.columns[0]",
                    "foreign_key_unknown_target_column",
                )
            ],
        ),
        (
            _fk(("customer_id", "small_id"), "customer"),
            [("tables[1].foreign_keys[0]", "foreign_key_column_count")],
        ),
        (_fk((), "customer"), [("tables[1].foreign_keys[0].columns", "empty_foreign_key")]),
        (
            _fk(("customer_id",), "customer", ()),
            [("tables[1].foreign_keys[0].references.columns", "empty_foreign_key")],
        ),
        (
            _fk(("customer_id", "customer_id"), "customer", ("id", "email")),
            [("tables[1].foreign_keys[0].columns[1]", "foreign_key_duplicate_column")],
        ),
        (
            _fk(("customer_email",), "customer", ("email",)),
            [("tables[1].foreign_keys[0].references.columns", "foreign_key_target_not_key")],
        ),
        (
            _fk(("small_id",), "customer"),
            [("tables[1].foreign_keys[0].columns[0]", "foreign_key_type_mismatch")],
        ),
    ],
)
def test_foreign_key_rules(key: ForeignKeyDraft, expected: list[tuple[str, str]]) -> None:
    assert _violations(CUSTOMER, _invoice(key)) == expected


def test_repeated_foreign_key() -> None:
    assert _violations(
        CUSTOMER,
        _invoice(_fk(("customer_id",), "customer"), _fk(("customer_id",), "customer")),
    ) == [("tables[1].foreign_keys[1]", "foreign_key_duplicate")]


def test_foreign_key_violations_follow_table_violations() -> None:
    broken = _related(2, "payment", key=("code",))

    assert _violations(CUSTOMER, _invoice(_fk(("customer_id",), "client")), broken) == [
        ("tables[2].primary_key[0]", "primary_key_unknown_column"),
        ("tables[1].foreign_keys[0].references.table", "foreign_key_unknown_table"),
    ]


def test_invalid_target_table_is_not_checked() -> None:
    broken = replace(CUSTOMER, primary_key=("code",))

    assert _violations(broken, _invoice(_fk(("customer_id",), "customer", ("uid",)))) == [
        ("tables[0].primary_key[0]", "primary_key_unknown_column")
    ]


def test_excluded_target_table_is_not_unknown() -> None:
    draft = DataModelDraft((_invoice(_fk(("customer_id",), "customer")),), excluded=("customer",))

    assert DataModelFactory().create(draft).tables[0].foreign_keys == ()


def test_relation_violation_order_is_stable() -> None:
    draft = (
        _related(0, "customer", *CUSTOMER.columns, unique=(("email", "email"), ("id",))),
        _invoice(_fk(("small_id",), "customer"), _fk(("customer_id",), "client")),
    )

    assert _violations(*draft) == _violations(*draft)
