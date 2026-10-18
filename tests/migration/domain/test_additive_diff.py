"""Добавляющая разница моделей: новые таблицы и колонки, все неаддитивные изменения сразу."""

from __future__ import annotations

import pytest

from forge.migration.domain.additive_diff import AdditiveDiff
from forge.migration.domain.changes import AddColumn, CreateTable, NonAdditiveChangeError
from forge.modeling.domain.data_model import DataModel
from tests.migration.models import CUSTOMER, INVOICE, model


def _rejected(accepted: DataModel, attempt: DataModel) -> list[tuple[str, str, str | None]]:
    with pytest.raises(NonAdditiveChangeError) as caught:
        AdditiveDiff().between(accepted, attempt)
    return [(c.code, c.table, c.column) for c in caught.value.changes]


def _describe(accepted: DataModel, attempt: DataModel) -> list[str]:
    result = []
    for change in AdditiveDiff().between(accepted, attempt):
        if isinstance(change, CreateTable):
            result.append(f"create {change.table.name}")
        else:
            null = "null" if change.nullable else "not null"
            result.append(f"add {change.table}.{change.column.name} {null}")
    return result


def test_first_operation_creates_every_table_in_model_order() -> None:
    assert _describe(model(), model(INVOICE + CUSTOMER)) == ["create invoice", "create customer"]


def test_new_column_of_existing_table() -> None:
    attempt = model(
        CUSTOMER.replace("    primary_key", "      - {name: phone, type: text}\n    primary_key")
    )

    assert _describe(model(CUSTOMER), attempt) == ["add customer.phone null"]


def test_new_not_null_column_keeps_nullability() -> None:
    attempt = model(
        CUSTOMER.replace(
            "    primary_key",
            "      - {name: code, type: integer, nullable: false}\n    primary_key",
        )
    )

    (change,) = AdditiveDiff().between(model(CUSTOMER), attempt)
    assert isinstance(change, AddColumn)
    assert change.nullable is False


def test_new_table_and_new_column_follow_attempt_order() -> None:
    attempt = model(
        INVOICE
        + CUSTOMER.replace("    primary_key", "      - {name: phone, type: text}\n    primary_key")
    )

    assert _describe(model(CUSTOMER), attempt) == ["create invoice", "add customer.phone null"]


def test_same_models_give_no_changes() -> None:
    assert AdditiveDiff().between(model(CUSTOMER), model(CUSTOMER)) == ()


def test_column_order_is_not_a_change() -> None:
    reordered = """
  - name: customer
    columns:
      - {name: email, type: string, length: 255, nullable: false}
      - {name: id, type: uuid}
    primary_key: [id]
"""
    assert AdditiveDiff().between(model(CUSTOMER), model(reordered)) == ()


def test_explicit_not_null_on_key_column_is_not_a_change() -> None:
    explicit = CUSTOMER.replace("{name: id, type: uuid}", "{name: id, type: uuid, nullable: false}")

    assert AdditiveDiff().between(model(CUSTOMER), model(explicit)) == ()


def test_table_removed() -> None:
    assert _rejected(model(CUSTOMER + INVOICE), model(CUSTOMER)) == [
        ("table_removed", "invoice", None)
    ]


def test_column_removed() -> None:
    attempt = model(
        CUSTOMER.replace("      - {name: email, type: string, length: 255, nullable: false}\n", "")
    )

    assert _rejected(model(CUSTOMER), attempt) == [("column_removed", "customer", "email")]


def test_rename_is_removal() -> None:
    attempt = model(CUSTOMER.replace("name: email", "name: mail"))

    assert _rejected(model(CUSTOMER), attempt) == [("column_removed", "customer", "email")]


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


def test_all_non_additive_changes_are_reported_together() -> None:
    attempt = model(
        CUSTOMER.replace("type: string, length: 255", "type: text")
        + INVOICE.replace("primary_key: [number]", "primary_key: [number, total]")
    )

    assert _rejected(model(CUSTOMER + INVOICE), attempt) == [
        ("column_type_changed", "customer", "email"),
        ("column_nullable_changed", "invoice", "total"),
        ("primary_key_changed", "invoice", None),
    ]


def test_messages_name_old_and_new_values() -> None:
    attempt = model(CUSTOMER.replace("type: string, length: 255", "type: string, length: 320"))

    with pytest.raises(NonAdditiveChangeError) as caught:
        AdditiveDiff().between(model(CUSTOMER), attempt)

    assert "string(255) → string(320)" in caught.value.changes[0].message
