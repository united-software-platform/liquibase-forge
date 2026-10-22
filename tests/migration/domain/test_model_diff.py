"""Разница моделей: новые и удалённые таблицы и колонки, все неподдерживаемые изменения сразу."""

from __future__ import annotations

import pytest

from forge.migration.domain.changes import (
    AddColumn,
    AddForeignKey,
    AddUnique,
    CreateTable,
    DropColumn,
    DropForeignKey,
    DropTable,
    DropUnique,
    UnsupportedChangeError,
)
from forge.migration.domain.model_diff import ModelDiff
from forge.modeling.domain.data_model import DataModel
from tests.migration.models import CUSTOMER, INVOICE, model

ITEM = """
  - name: item
    columns:
      - {name: sku, type: text}
    primary_key: [sku]
"""

CUSTOMER_WITHOUT_EMAIL = """
  - name: customer
    columns:
      - {name: id, type: uuid}
      - {name: phone, type: text}
    primary_key: [id]
"""

WITHOUT_EMAIL = CUSTOMER.replace(
    "      - {name: email, type: string, length: 255, nullable: false}\n", ""
)
WITH_PHONE = CUSTOMER.replace(
    "    primary_key", "      - {name: phone, type: text}\n    primary_key"
)


def _rejected(accepted: DataModel, attempt: DataModel) -> list[tuple[str, str, str | None]]:
    with pytest.raises(UnsupportedChangeError) as caught:
        ModelDiff().between(accepted, attempt)
    return [(c.code, c.table, c.column) for c in caught.value.changes]


def _describe(accepted: DataModel, attempt: DataModel) -> list[str]:
    result = []
    for change in ModelDiff().between(accepted, attempt):
        if isinstance(change, CreateTable):
            result.append(f"create {change.table.name}")
        elif isinstance(change, DropTable):
            result.append(f"drop table {change.table.name}")
        elif isinstance(change, DropColumn):
            result.append(f"drop {change.table}.{change.column.name}")
        else:
            null = "null" if change.nullable else "not null"
            result.append(f"add {change.table}.{change.column.name} {null}")
    return result


def test_first_operation_creates_every_table_in_model_order() -> None:
    assert _describe(model(), model(INVOICE + CUSTOMER)) == ["create invoice", "create customer"]


def test_new_column_of_existing_table() -> None:
    assert _describe(model(CUSTOMER), model(WITH_PHONE)) == ["add customer.phone null"]


def test_new_not_null_column_keeps_nullability() -> None:
    attempt = model(
        CUSTOMER.replace(
            "    primary_key",
            "      - {name: code, type: integer, nullable: false}\n    primary_key",
        )
    )

    (change,) = ModelDiff().between(model(CUSTOMER), attempt)
    assert isinstance(change, AddColumn)
    assert change.nullable is False


def test_new_table_and_new_column_follow_attempt_order() -> None:
    assert _describe(model(CUSTOMER), model(INVOICE + WITH_PHONE)) == [
        "create invoice",
        "add customer.phone null",
    ]


def test_same_models_give_no_changes() -> None:
    assert ModelDiff().between(model(CUSTOMER), model(CUSTOMER)) == ()


def test_column_order_is_not_a_change() -> None:
    reordered = """
  - name: customer
    columns:
      - {name: email, type: string, length: 255, nullable: false}
      - {name: id, type: uuid}
    primary_key: [id]
"""
    assert ModelDiff().between(model(CUSTOMER), model(reordered)) == ()


def test_explicit_not_null_on_key_column_is_not_a_change() -> None:
    explicit = CUSTOMER.replace("{name: id, type: uuid}", "{name: id, type: uuid, nullable: false}")

    assert ModelDiff().between(model(CUSTOMER), model(explicit)) == ()


def test_removed_table_is_dropped_without_its_columns() -> None:
    changes = ModelDiff().between(model(CUSTOMER + INVOICE), model(CUSTOMER))

    (change,) = changes
    assert isinstance(change, DropTable)
    assert change.table.name.value == "invoice"


def test_removed_column_is_dropped_with_its_nullability() -> None:
    (change,) = ModelDiff().between(model(CUSTOMER), model(WITHOUT_EMAIL))

    assert isinstance(change, DropColumn)
    assert (change.table.value, change.column.name.value, change.nullable) == (
        "customer",
        "email",
        False,
    )


def test_removed_nullable_column_keeps_nullability() -> None:
    (change,) = ModelDiff().between(model(WITH_PHONE), model(CUSTOMER))

    assert isinstance(change, DropColumn)
    assert change.nullable is True


def test_removed_primary_key_column_is_only_a_key_change() -> None:
    attempt = model(
        """
  - name: customer
    columns:
      - {name: email, type: string, length: 255, nullable: false}
    primary_key: [email]
"""
    )

    assert _rejected(model(CUSTOMER), attempt) == [("primary_key_changed", "customer", None)]


def test_rename_is_drop_and_add() -> None:
    attempt = model(CUSTOMER.replace("name: email", "name: mail"))

    assert _describe(model(CUSTOMER), attempt) == [
        "drop customer.email",
        "add customer.mail not null",
    ]


def test_drops_come_before_additions() -> None:
    assert _describe(model(CUSTOMER + INVOICE), model(ITEM + CUSTOMER_WITHOUT_EMAIL)) == [
        "drop table invoice",
        "drop customer.email",
        "create item",
        "add customer.phone null",
    ]


@pytest.mark.parametrize("replacement", ["type: string, length: 320", "type: text"])
def test_column_type_changed(replacement: str) -> None:
    attempt = model(CUSTOMER.replace("type: string, length: 255", replacement))

    assert _rejected(model(CUSTOMER), attempt) == [("column_type_changed", "customer", "email")]


def test_column_nullable_changed() -> None:
    attempt = model(CUSTOMER.replace(", nullable: false}", "}"))

    assert _rejected(model(CUSTOMER), attempt) == [("column_nullable_changed", "customer", "email")]


def test_primary_key_changed() -> None:
    attempt = model(CUSTOMER.replace("primary_key: [id]", "primary_key: [id, email]"))

    assert _rejected(model(CUSTOMER), attempt) == [("primary_key_changed", "customer", None)]


def test_primary_key_order_change_is_rejected() -> None:
    accepted = model(CUSTOMER.replace("primary_key: [id]", "primary_key: [id, email]"))
    attempt = model(CUSTOMER.replace("primary_key: [id]", "primary_key: [email, id]"))

    assert _rejected(accepted, attempt) == [("primary_key_changed", "customer", None)]


def test_all_unsupported_changes_are_reported_together() -> None:
    attempt = model(
        CUSTOMER.replace("type: string, length: 255", "type: text")
        + INVOICE.replace("primary_key: [number]", "primary_key: [number, total]")
    )

    assert _rejected(model(CUSTOMER + INVOICE), attempt) == [
        ("column_type_changed", "customer", "email"),
        ("column_nullable_changed", "invoice", "total"),
        ("primary_key_changed", "invoice", None),
    ]


def test_unsupported_change_blocks_drops_too() -> None:
    attempt = model(CUSTOMER.replace("type: string, length: 255", "type: text"))

    assert _rejected(model(CUSTOMER + INVOICE), attempt) == [
        ("column_type_changed", "customer", "email")
    ]


def test_messages_name_old_and_new_values() -> None:
    attempt = model(CUSTOMER.replace("type: string, length: 255", "type: string, length: 320"))

    with pytest.raises(UnsupportedChangeError) as caught:
        ModelDiff().between(model(CUSTOMER), attempt)

    assert "string(255) → string(320)" in caught.value.changes[0].message


SHOP = """
  - name: invoice
    columns:
      - {name: id, type: bigint}
      - {name: customer_id, type: uuid}
      - {name: customer_email, type: string, length: 255}
    primary_key: [id]
    foreign_keys:
      - {columns: [customer_id], references: {table: customer, columns: [id]}}
"""

SHOP_CUSTOMER = """
  - name: customer
    columns:
      - {name: id, type: uuid}
      - {name: email, type: string, length: 255, nullable: false}
      - {name: tenant_id, type: bigint}
      - {name: code, type: text}
    primary_key: [id]
    unique:
      - [email]
      - [tenant_id, code]
"""


def _constraints(accepted: DataModel, attempt: DataModel) -> list[str]:
    """Изменения схемы с ограничениями: вид, таблица и содержимое ограничения."""
    result = []
    for change in ModelDiff().between(accepted, attempt):
        if isinstance(change, AddUnique | DropUnique):
            verb = "add" if isinstance(change, AddUnique) else "drop"
            columns = ", ".join(column.value for column in change.unique.columns)
            result.append(f"{verb} unique {change.table}[{columns}]")
        elif isinstance(change, AddForeignKey | DropForeignKey):
            verb = "add" if isinstance(change, AddForeignKey) else "drop"
            result.append(f"{verb} fk {change.table} {change.key}")
        elif isinstance(change, CreateTable):
            result.append(f"create {change.table.name}")
        elif isinstance(change, DropTable):
            result.append(f"drop table {change.table.name}")
        elif isinstance(change, DropColumn):
            result.append(f"drop {change.table}.{change.column.name}")
        else:
            result.append(f"add {change.table}.{change.column.name}")
    return result


def test_new_table_constraints_follow_all_tables() -> None:
    # invoice стоит в модели раньше customer, на который ссылается
    assert _constraints(model(), model(SHOP + SHOP_CUSTOMER)) == [
        "create invoice",
        "create customer",
        "add unique customer[email]",
        "add unique customer[tenant_id, code]",
        "add fk invoice [customer_id] → customer[id]",
    ]


def test_new_foreign_key_of_existing_tables() -> None:
    without = SHOP.split("    foreign_keys:")[0]

    assert _constraints(model(without + SHOP_CUSTOMER), model(SHOP + SHOP_CUSTOMER)) == [
        "add fk invoice [customer_id] → customer[id]"
    ]


def test_reordered_constraints_give_no_changes() -> None:
    reordered = SHOP_CUSTOMER.replace(
        "      - [email]\n      - [tenant_id, code]\n",
        "      - [code, tenant_id]\n      - [email]\n",
    )

    assert _constraints(model(SHOP + SHOP_CUSTOMER), model(SHOP + reordered)) == []


def test_changed_foreign_key_target_is_drop_and_add() -> None:
    to_email = SHOP.replace(
        "{columns: [customer_id], references: {table: customer, columns: [id]}}",
        "{columns: [customer_email], references: {table: customer, columns: [email]}}",
    )

    assert _constraints(model(SHOP + SHOP_CUSTOMER), model(to_email + SHOP_CUSTOMER)) == [
        "drop fk invoice [customer_id] → customer[id]",
        "add fk invoice [customer_email] → customer[email]",
    ]


def test_foreign_key_to_new_unique_set_comes_after_it() -> None:
    plain = SHOP_CUSTOMER.split("    unique:")[0]
    without = SHOP.split("    foreign_keys:")[0]
    to_email = (
        without
        + "    foreign_keys:\n"
        + "      - {columns: [customer_email], references: {table: customer, columns: [email]}}\n"
    )
    with_email = plain + "    unique:\n      - [email]\n"

    assert _constraints(model(without + plain), model(to_email + with_email)) == [
        "add unique customer[email]",
        "add fk invoice [customer_email] → customer[email]",
    ]


def test_dropped_tables_drop_their_foreign_keys_first() -> None:
    assert _constraints(model(SHOP + SHOP_CUSTOMER), model()) == [
        "drop fk invoice [customer_id] → customer[id]",
        "drop table invoice",
        "drop table customer",
    ]


def test_dropped_target_table_drops_foreign_keys_on_it() -> None:
    without = SHOP.split("    foreign_keys:")[0]
    category = """
  - name: category
    columns:
      - {name: id, type: bigint}
      - {name: parent_id, type: bigint}
    primary_key: [id]
    foreign_keys:
      - {columns: [parent_id], references: {table: category, columns: [id]}}
"""

    assert _constraints(model(SHOP + SHOP_CUSTOMER + category), model(without)) == [
        "drop fk invoice [customer_id] → customer[id]",
        "drop fk category [parent_id] → category[id]",
        "drop table customer",
        "drop table category",
    ]


def test_dropped_column_drops_its_unique_set_first() -> None:
    without_email = SHOP_CUSTOMER.replace(
        "      - {name: email, type: string, length: 255, nullable: false}\n", ""
    ).replace("      - [email]\n", "")

    assert _constraints(model(SHOP_CUSTOMER), model(without_email)) == [
        "drop unique customer[email]",
        "drop customer.email",
    ]


def test_all_groups_are_ordered() -> None:
    accepted = model(SHOP + SHOP_CUSTOMER + ITEM)
    customer = (
        SHOP_CUSTOMER.replace("      - {name: code, type: text}\n", "")
        .replace("      - [tenant_id, code]\n", "      - [tenant_id]\n")
        .replace("    primary_key: [id]", "      - {name: note, type: text}\n    primary_key: [id]")
    )
    payment = """
  - name: payment
    columns:
      - {name: id, type: bigint}
      - {name: customer_id, type: uuid}
    primary_key: [id]
    foreign_keys:
      - {columns: [customer_id], references: {table: customer, columns: [id]}}
"""

    assert _constraints(accepted, model(payment + customer)) == [
        "drop fk invoice [customer_id] → customer[id]",
        "drop unique customer[tenant_id, code]",
        "drop table invoice",
        "drop table item",
        "drop customer.code",
        "create payment",
        "add customer.note",
        "add unique customer[tenant_id]",
        "add fk payment [customer_id] → customer[id]",
    ]
