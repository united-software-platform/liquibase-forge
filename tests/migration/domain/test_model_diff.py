"""Разница моделей: новые и удалённые таблицы и колонки, все неподдерживаемые изменения сразу."""

from __future__ import annotations

import pytest

from forge.migration.domain.changes import (
    AddColumn,
    CreateTable,
    DropColumn,
    DropTable,
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
