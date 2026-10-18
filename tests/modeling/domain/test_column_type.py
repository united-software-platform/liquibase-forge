"""Тип колонки: перечень типов, обязательные и чужие параметры, диапазоны."""

from __future__ import annotations

import pytest

from forge.modeling.domain.column_type import ColumnType, TypeKind
from forge.modeling.domain.violation import ModelViolationError


def _violations(
    name: str,
    *,
    length: int | None = None,
    precision: int | None = None,
    scale: int | None = None,
) -> list[tuple[str, str]]:
    with pytest.raises(ModelViolationError) as caught:
        ColumnType.of(name, length=length, precision=precision, scale=scale)
    return [(v.path, v.code) for v in caught.value.violations]


@pytest.mark.parametrize(
    "name", ["integer", "bigint", "boolean", "text", "date", "timestamp", "timestamp_tz", "uuid"]
)
def test_type_without_parameters(name: str) -> None:
    column_type = ColumnType.of(name)

    assert column_type.kind == TypeKind(name)
    assert column_type.parameters() == {"length": None, "precision": None, "scale": None}


def test_all_ten_types_are_listed() -> None:
    assert [kind.value for kind in TypeKind] == [
        "integer",
        "bigint",
        "boolean",
        "string",
        "text",
        "decimal",
        "date",
        "timestamp",
        "timestamp_tz",
        "uuid",
    ]


def test_string_with_length() -> None:
    assert ColumnType.of("string", length=255).length == 255


@pytest.mark.parametrize("length", [1, 10_485_760])
def test_string_length_bounds(length: int) -> None:
    assert ColumnType.of("string", length=length).length == length


def test_decimal_with_precision_and_scale() -> None:
    column_type = ColumnType.of("decimal", precision=12, scale=2)

    assert (column_type.precision, column_type.scale) == (12, 2)


@pytest.mark.parametrize(("precision", "scale"), [(1, 0), (1000, 1000), (5, 5)])
def test_decimal_bounds(precision: int, scale: int) -> None:
    assert ColumnType.of("decimal", precision=precision, scale=scale).scale == scale


def test_unknown_type() -> None:
    assert _violations("varchar") == [("type", "unknown_type")]


def test_string_without_length() -> None:
    assert _violations("string") == [("length", "missing_type_parameter")]


def test_decimal_without_parameters_reports_both() -> None:
    assert _violations("decimal") == [
        ("precision", "missing_type_parameter"),
        ("scale", "missing_type_parameter"),
    ]


def test_foreign_parameter() -> None:
    assert _violations("integer", length=10) == [("length", "unexpected_type_parameter")]


@pytest.mark.parametrize("length", [0, -1, 10_485_761])
def test_string_length_out_of_range(length: int) -> None:
    assert _violations("string", length=length) == [("length", "type_parameter_out_of_range")]


def test_scale_greater_than_precision() -> None:
    assert _violations("decimal", precision=5, scale=6) == [
        ("scale", "type_parameter_out_of_range")
    ]


def test_negative_scale_with_invalid_precision_reports_both() -> None:
    assert _violations("decimal", precision=0, scale=-1) == [
        ("precision", "type_parameter_out_of_range"),
        ("scale", "type_parameter_out_of_range"),
    ]


def test_several_violations_of_one_type_are_reported_together() -> None:
    assert _violations("string", length=0, precision=3) == [
        ("precision", "unexpected_type_parameter"),
        ("length", "type_parameter_out_of_range"),
    ]
