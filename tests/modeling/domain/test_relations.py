"""Наборы уникальности и внешние ключи: тождество по содержимому и инварианты."""

from __future__ import annotations

import pytest

from forge.modeling.domain.column import Column
from forge.modeling.domain.column_type import parse_column_type
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.foreign_key import ForeignKey
from forge.modeling.domain.identifier import ColumnName, TableName
from forge.modeling.domain.primary_key import PrimaryKey
from forge.modeling.domain.table import Table
from forge.modeling.domain.unique_set import UniqueSet
from forge.modeling.domain.violation import ModelViolationError


def _names(*names: str) -> tuple[ColumnName, ...]:
    return tuple(ColumnName(name) for name in names)


def _fk(columns: tuple[str, ...], target: str, target_columns: tuple[str, ...]) -> ForeignKey:
    return ForeignKey(_names(*columns), TableName(target), _names(*target_columns))


def _table(
    name: str,
    *columns: str,
    unique: tuple[UniqueSet, ...] = (),
    foreign_keys: tuple[ForeignKey, ...] = (),
) -> Table:
    return Table(
        TableName(name),
        tuple(Column(ColumnName(column), parse_column_type("bigint")) for column in columns),
        PrimaryKey(_names("id")),
        unique,
        foreign_keys,
    )


def _codes(error: pytest.ExceptionInfo[ModelViolationError]) -> list[tuple[str, str]]:
    return [(v.path, v.code) for v in error.value.violations]


def test_unique_set_equality_ignores_order() -> None:
    assert UniqueSet(_names("a", "b")) == UniqueSet(_names("b", "a"))
    assert hash(UniqueSet(_names("a", "b"))) == hash(UniqueSet(_names("b", "a")))
    assert UniqueSet(_names("a")) != UniqueSet(_names("a", "b"))


def test_foreign_key_equality_ignores_pair_order() -> None:
    first = _fk(("a", "b"), "line", ("x", "y"))
    second = _fk(("b", "a"), "line", ("y", "x"))

    assert first == second
    assert hash(first) == hash(second)
    assert first != _fk(("a", "b"), "line", ("y", "x"))
    assert first != _fk(("a", "b"), "other", ("x", "y"))


def test_unique_set_list_invariants() -> None:
    with pytest.raises(ModelViolationError) as empty:
        UniqueSet(())
    with pytest.raises(ModelViolationError) as repeated:
        UniqueSet(_names("code", "code"))

    assert _codes(empty) == [("", "empty_unique")]
    assert _codes(repeated) == [("[1]", "unique_duplicate_column")]


def test_foreign_key_list_invariants() -> None:
    with pytest.raises(ModelViolationError) as empty:
        ForeignKey((), TableName("customer"), _names("id"))
    with pytest.raises(ModelViolationError) as repeated:
        _fk(("a", "a"), "customer", ("x", "y"))
    with pytest.raises(ModelViolationError) as count:
        _fk(("a", "b"), "customer", ("x",))

    assert _codes(empty) == [("columns", "empty_foreign_key")]
    assert _codes(repeated) == [("columns[1]", "foreign_key_duplicate_column")]
    assert _codes(count) == [("", "foreign_key_column_count")]


def test_table_keeps_relations() -> None:
    table = _table(
        "category",
        "id",
        "parent_id",
        "code",
        unique=(UniqueSet(_names("code")),),
        foreign_keys=(_fk(("parent_id",), "category", ("id",)),),
    )

    assert table.has_key(frozenset(_names("id")))
    assert table.has_key(frozenset(_names("code")))
    assert not table.has_key(frozenset(_names("parent_id")))


def test_table_rejects_foreign_key_on_unknown_column_and_repeated_key() -> None:
    key = _fk(("parent_id",), "category", ("id",))

    with pytest.raises(ModelViolationError) as unknown:
        _table("category", "id", foreign_keys=(key,))
    with pytest.raises(ModelViolationError) as repeated:
        _table("category", "id", "parent_id", foreign_keys=(key, key))

    assert _codes(unknown) == [("foreign_keys[0].columns[0]", "foreign_key_unknown_column")]
    assert _codes(repeated) == [("foreign_keys[1]", "foreign_key_duplicate")]


def test_model_checks_foreign_key_target() -> None:
    invoice = _table(
        "invoice", "id", "customer_id", foreign_keys=(_fk(("customer_id",), "customer", ("id",)),)
    )

    with pytest.raises(ModelViolationError) as missing:
        DataModel((invoice,))

    assert _codes(missing) == [
        ("tables[0].foreign_keys[0].references.table", "foreign_key_unknown_table")
    ]
    assert DataModel((invoice, _table("customer", "id"))).tables[0] == invoice
