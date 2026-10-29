"""Разница моделей: перечни значений по содержимому и отклонение смены генерации значения."""

from __future__ import annotations

import pytest

from forge.migration.domain.changes import (
    AddCheck,
    AddColumn,
    AddUnique,
    CreateTable,
    DropCheck,
    DropColumn,
    DropUnique,
    UnsupportedChangeError,
)
from forge.migration.domain.model_diff import ModelDiff
from forge.modeling.domain.identifier import ColumnName
from forge.modeling.domain.value_list import ValueList
from tests.migration.models import model


def _event(source: str = "", extra: str = "", key_generated: str = "") -> str:
    return f"""
  - name: event
    columns:
      - {{name: id, type: bigint{key_generated}}}
      - {{name: source, type: text{source}}}
{extra}    primary_key: [id]
"""


def _kinds(accepted: str, attempt: str) -> list[str]:
    return [type(c).__name__ for c in ModelDiff().between(model(accepted), model(attempt))]


def test_new_table_with_check_creates_table_then_check() -> None:
    changes = ModelDiff().between(model(), model(_event(", check: [manual, collector]")))

    assert [type(c) for c in changes] == [CreateTable, AddCheck]
    check = changes[1]
    assert isinstance(check, AddCheck)
    assert (check.column, check.values) == (
        ColumnName("source"),
        ValueList(("collector", "manual")),
    )


def test_value_order_does_not_change_check() -> None:
    accepted = _event(", check: [collector, manual]")
    attempt = _event(", check: [manual, collector]")

    assert _kinds(accepted, attempt) == []


def test_extended_check_is_dropped_and_added() -> None:
    accepted = _event(", check: [collector, manual]")
    attempt = _event(", check: [collector, manual, import]")

    assert _kinds(accepted, attempt) == ["DropCheck", "AddCheck"]


def test_new_column_with_check_is_added_before_its_check() -> None:
    attempt = _event(extra="      - {name: channel, type: text, check: [web, api]}\n")

    assert _kinds(_event(), attempt) == ["AddColumn", "AddCheck"]


def test_dropped_column_with_check_drops_check_first() -> None:
    accepted = _event(extra="      - {name: channel, type: text, check: [web, api]}\n")

    changes = ModelDiff().between(model(accepted), model(_event()))

    assert [type(c) for c in changes] == [DropCheck, DropColumn]


def test_check_groups_follow_unique_groups() -> None:
    accepted = _event(", check: [a]").replace(
        "    primary_key", "    unique: [[source]]\n    primary_key"
    )
    attempt = _event(", check: [b]").replace(
        "    primary_key", "      - {name: code, type: text}\n    unique: [[code]]\n    primary_key"
    )

    assert [type(c) for c in ModelDiff().between(model(accepted), model(attempt))] == [
        DropUnique,
        DropCheck,
        AddColumn,
        AddUnique,
        AddCheck,
    ]


def test_dropped_table_does_not_drop_its_checks_separately() -> None:
    assert _kinds(_event(", check: [a]"), "") == ["DropTable"]


@pytest.mark.parametrize(
    ("accepted", "attempt"),
    [
        (_event(), _event(key_generated=", generated: identity")),
        (_event(key_generated=", generated: identity"), _event()),
    ],
)
def test_generation_change_is_unsupported(accepted: str, attempt: str) -> None:
    with pytest.raises(UnsupportedChangeError) as caught:
        ModelDiff().between(model(accepted), model(attempt))

    assert [(c.code, c.table, c.column) for c in caught.value.changes] == [
        ("column_generated_changed", "event", "id")
    ]


def test_generation_change_hides_only_its_own_nullable_change() -> None:
    accepted = _event(extra="      - {name: seq_no, type: integer}\n")
    attempt = _event(extra="      - {name: seq_no, type: integer, generated: identity}\n")

    with pytest.raises(UnsupportedChangeError) as caught:
        ModelDiff().between(model(accepted), model(attempt))

    assert [c.code for c in caught.value.changes] == ["column_generated_changed"]


def test_new_column_with_generation_is_added() -> None:
    attempt = _event(extra="      - {name: seq_no, type: integer, generated: identity}\n")

    (change,) = ModelDiff().between(model(_event()), model(attempt))

    assert isinstance(change, AddColumn)
    assert change.nullable is False
