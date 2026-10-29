"""Сравнение фактической схемы с моделью: каждый вид расхождения и порядок."""

from __future__ import annotations

import pytest

from forge.modeling.domain.column_type import parse_column_type
from forge.reconciliation.domain.actual_schema import (
    ActualCheck,
    ActualColumn,
    ActualForeignKey,
    ActualTable,
)
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


EVENT_MODEL = """
  - name: event
    columns:
      - {name: id, type: bigint, generated: identity}
      - {name: source, type: text, check: [collector, manual]}
      - {name: priority, type: integer, check: [1, 2]}
    primary_key: [id]
"""
SOURCE = ActualCheck("CHECK (...)", "source", frozenset({"manual", "collector"}))
PRIORITY = ActualCheck("CHECK (...)", "priority", frozenset({2, 1}))


def _event(*checks: ActualCheck, generated: str | None = "identity") -> ActualTable:
    columns = (
        ActualColumn("id", parse_column_type("bigint"), "bigint", False, generated),
        column("source", "text"),
        column("priority", "integer"),
    )
    return ActualTable("event", columns, ("id",), checks=checks)


def _events(table: ActualTable) -> list[tuple[str, ...]]:
    return _found(table, tables_of_model=EVENT_MODEL)


def test_matching_generation_and_checks() -> None:
    assert _events(_event(PRIORITY, SOURCE)) == []


@pytest.mark.parametrize(
    ("generated", "expected", "actual"),
    [(None, "identity", "absent"), ("identity_always", "identity", "identity_always")],
)
def test_generation_mismatch(generated: str | None, expected: str, actual: str) -> None:
    assert _events(_event(SOURCE, PRIORITY, generated=generated)) == [
        ("column_generated_mismatch", "event", "id", expected, actual)
    ]


def test_unexpected_generation() -> None:
    table = ActualTable(
        "customer",
        (
            ActualColumn("id", parse_column_type("uuid"), "uuid", False, "identity"),
            column("email", "string", nullable=False, length=255),
        ),
        ("id",),
    )

    assert _found(table) == [("column_generated_mismatch", "customer", "id", "absent", "identity")]


def test_check_missing_and_other_values() -> None:
    wider = ActualCheck("CHECK (...)", "source", frozenset({"collector", "manual", "import"}))

    assert _events(_event(wider)) == [
        ("check_missing", "event", "source", "[collector, manual]", "absent"),
        ("check_missing", "event", "priority", "[1, 2]", "absent"),
        ("check_unexpected", "event", "source", "absent", "[collector, import, manual]"),
    ]


def test_unrecognized_check_is_unexpected() -> None:
    expression = ActualCheck("CHECK ((priority > 0))")

    assert _events(_event(SOURCE, PRIORITY, expression)) == [
        ("check_unexpected", "event", "", "absent", "CHECK ((priority > 0))")
    ]


def test_value_kind_matters() -> None:
    as_text = ActualCheck("CHECK (...)", "priority", frozenset({"1", "2"}))

    assert [kind for kind, *_ in _events(_event(SOURCE, as_text))] == [
        "check_missing",
        "check_unexpected",
    ]


def test_checks_go_between_unique_and_foreign_keys() -> None:
    linked = EVENT_MODEL.replace(
        "    primary_key: [id]",
        "      - {name: parent_id, type: bigint}\n    primary_key: [id]\n    unique: [[source]]\n"
        "    foreign_keys:\n"
        "      - {columns: [parent_id], references: {table: event, columns: [id]}}",
    )
    table = ActualTable("event", (*_event().columns, column("parent_id", "bigint")), ("id",))

    kinds = [kind for kind, *_ in _found(table, tables_of_model=linked)]

    assert kinds == ["unique_missing", "check_missing", "check_missing", "foreign_key_missing"]
