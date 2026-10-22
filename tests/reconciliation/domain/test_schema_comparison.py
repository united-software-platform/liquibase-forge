"""Сравнение фактической схемы с моделью: каждый вид расхождения и порядок."""

from __future__ import annotations

from forge.reconciliation.domain.actual_schema import ActualColumn, ActualForeignKey, ActualTable
from forge.reconciliation.domain.schema_comparison import SchemaComparison
from tests.migration.models import CUSTOMER, INVOICE, model
from tests.reconciliation.schemas import column, customer, schema

INVOICE_TABLE = ActualTable(
    "invoice",
    (
        column("number", "bigint", nullable=False),
        column("total", "decimal", precision=12, scale=2),
    ),
    ("number",),
)


def _found(*tables: ActualTable, tables_of_model: str = CUSTOMER) -> list[tuple[str, ...]]:
    result = SchemaComparison().compare(model(tables_of_model), schema(*tables))
    return [(d.kind, d.table or "", d.column or "", d.expected, d.actual) for d in result]


def test_matching_schema() -> None:
    assert _found(customer(), INVOICE_TABLE, tables_of_model=CUSTOMER + INVOICE) == []


def test_column_order_is_not_compared() -> None:
    reordered = ActualTable("customer", tuple(reversed(customer().columns)), ("id",))

    assert _found(reordered) == []


def test_table_missing_hides_its_columns() -> None:
    assert _found(customer(), tables_of_model=CUSTOMER + INVOICE) == [
        ("table_missing", "invoice", "", "present", "absent")
    ]


def test_table_unexpected() -> None:
    assert _found(customer(), INVOICE_TABLE) == [
        ("table_unexpected", "invoice", "", "absent", "present")
    ]


def test_column_missing() -> None:
    table = ActualTable("customer", (column("id", "uuid", nullable=False),), ("id",))

    assert _found(table) == [("column_missing", "customer", "email", "string(255)", "absent")]


def test_column_unexpected() -> None:
    assert _found(customer(column("legacy", "text"))) == [
        ("column_unexpected", "customer", "legacy", "absent", "text")
    ]


def test_column_type_mismatch() -> None:
    table = ActualTable(
        "customer",
        (
            column("id", "uuid", nullable=False),
            column("email", "string", nullable=False, length=320),
        ),
        ("id",),
    )

    assert _found(table) == [
        ("column_type_mismatch", "customer", "email", "string(255)", "string(320)")
    ]


def test_type_outside_format() -> None:
    table = ActualTable(
        "customer",
        (column("id", "uuid", nullable=False), ActualColumn("email", None, "smallint", False)),
        ("id",),
    )

    assert _found(table) == [
        ("column_type_mismatch", "customer", "email", "string(255)", "smallint")
    ]


def test_column_nullable_mismatch() -> None:
    table = ActualTable(
        "customer",
        (column("id", "uuid", nullable=False), column("email", "string", length=255)),
        ("id",),
    )

    assert _found(table) == [("column_nullable_mismatch", "customer", "email", "NOT NULL", "NULL")]


def test_primary_key_order() -> None:
    accepted = CUSTOMER.replace("primary_key: [id]", "primary_key: [id, email]")

    assert _found(customer(key=("email", "id")), tables_of_model=accepted) == [
        ("primary_key_mismatch", "customer", "", "[id, email]", "[email, id]")
    ]


def test_primary_key_absent() -> None:
    assert _found(customer(key=None)) == [
        ("primary_key_mismatch", "customer", "", "[id]", "absent")
    ]


def test_order_of_discrepancies_is_stable() -> None:
    table = ActualTable(
        "customer",
        (
            column("zeta", "text"),
            column("email", "text", nullable=True),
            column("alpha", "text"),
        ),
        None,
    )

    found = _found(table, ActualTable("b_extra", (), None), ActualTable("a_extra", (), None))

    assert [(kind, t, c) for kind, t, c, _, _ in found] == [
        ("column_missing", "customer", "id"),
        ("column_type_mismatch", "customer", "email"),
        ("column_nullable_mismatch", "customer", "email"),
        ("column_unexpected", "customer", "alpha"),
        ("column_unexpected", "customer", "zeta"),
        ("primary_key_mismatch", "customer", ""),
        ("table_unexpected", "a_extra", ""),
        ("table_unexpected", "b_extra", ""),
    ]


LINKED_MODEL = (
    (
        CUSTOMER + "      - {name: tenant_id, type: bigint}\n      - {name: code, type: text}\n"
    ).replace("    primary_key: [id]\n", "")
    + ("    primary_key: [id]\n    unique:\n      - [email]\n      - [tenant_id, code]\n")
    + """
  - name: invoice
    columns:
      - {name: id, type: bigint}
      - {name: customer_id, type: uuid}
    primary_key: [id]
    foreign_keys:
      - {columns: [customer_id], references: {table: customer, columns: [id]}}
"""
)
TO_CUSTOMER = ActualForeignKey(("customer_id",), "customer", ("id",))


def _linked_customer(*unique: tuple[str, ...]) -> ActualTable:
    columns = customer(column("tenant_id", "bigint"), column("code", "text")).columns
    return ActualTable("customer", columns, ("id",), unique)


def _invoice(*keys: ActualForeignKey) -> ActualTable:
    columns = (column("id", "bigint", nullable=False), column("customer_id", "uuid"))
    return ActualTable("invoice", columns, ("id",), foreign_keys=keys)


def _linked(*tables: ActualTable) -> list[tuple[str, ...]]:
    return _found(*tables, tables_of_model=LINKED_MODEL)


def test_matching_constraints_by_content() -> None:
    # Порядок колонок набора в БД другой, имя ограничения не сравнивается
    assert _linked(_linked_customer(("code", "tenant_id"), ("email",)), _invoice(TO_CUSTOMER)) == []


def test_constraints_missing() -> None:
    assert _linked(_linked_customer(("email",)), _invoice()) == [
        ("unique_missing", "customer", "", "[tenant_id, code]", "absent"),
        ("foreign_key_missing", "invoice", "", "[customer_id] → customer[id]", "absent"),
    ]


def test_constraints_unexpected() -> None:
    extra = ActualForeignKey(("id",), "customer", ("tenant_id",))
    table = _linked_customer(("email",), ("tenant_id", "code"), ("tenant_id",), ("code",))

    assert _linked(table, _invoice(TO_CUSTOMER, extra)) == [
        ("unique_unexpected", "customer", "", "absent", "[code]"),
        ("unique_unexpected", "customer", "", "absent", "[tenant_id]"),
        ("foreign_key_unexpected", "invoice", "", "absent", "[id] → customer[tenant_id]"),
    ]


def test_constraints_follow_primary_key_in_order() -> None:
    table = ActualTable("customer", _linked_customer().columns, None, (("code",),))

    assert [kind for kind, *_ in _linked(table, _invoice(TO_CUSTOMER))] == [
        "primary_key_mismatch",
        "unique_missing",
        "unique_missing",
        "unique_unexpected",
    ]


def test_missing_table_gives_no_constraint_discrepancies() -> None:
    assert _linked(_linked_customer(("email",), ("tenant_id", "code"))) == [
        ("table_missing", "invoice", "", "present", "absent")
    ]


def test_constraint_comparison_is_stable() -> None:
    tables = (_linked_customer(("code",)), _invoice(ActualForeignKey(("id",), "x", ("y",))))

    assert _linked(*tables) == _linked(*tables)
