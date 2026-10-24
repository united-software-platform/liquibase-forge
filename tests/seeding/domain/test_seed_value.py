"""Значения seed по типам колонок: сценарии требований о значениях `forge-seed-data`."""

from __future__ import annotations

import pytest

from forge.modeling.domain.column_type import ColumnType, TypeKind
from forge.modeling.domain.violation import Violation
from forge.seeding.domain.draft import RawValue, ScalarKind
from forge.seeding.domain.seed_value import SeedValue, SeedValueFactory
from tests.seeding.support import NULL, b, f, i, s, ts

INTEGER = ColumnType(TypeKind.INTEGER)
BIGINT = ColumnType(TypeKind.BIGINT)
BOOLEAN = ColumnType(TypeKind.BOOLEAN)
CODE = ColumnType(TypeKind.STRING, length=8)
TEXT = ColumnType(TypeKind.TEXT)
FEE = ColumnType(TypeKind.DECIMAL, precision=12, scale=2)
DATE = ColumnType(TypeKind.DATE)
TIMESTAMP = ColumnType(TypeKind.TIMESTAMP)
TIMESTAMP_TZ = ColumnType(TypeKind.TIMESTAMP_TZ)
UUID = ColumnType(TypeKind.UUID)


def _value(column_type: ColumnType, raw: RawValue) -> SeedValue:
    value = SeedValueFactory().create(column_type, raw)
    assert isinstance(value, SeedValue), value
    return value


def _code(column_type: ColumnType, raw: RawValue) -> str:
    violation = SeedValueFactory().create(column_type, raw)
    assert isinstance(violation, Violation), violation
    assert violation.path == ""
    return violation.code


@pytest.mark.parametrize(
    ("column_type", "raw", "form"),
    [
        (INTEGER, i(10), 10),
        (INTEGER, i(-(2**31)), -(2**31)),
        (BIGINT, i(2**63 - 1), 2**63 - 1),
        (BOOLEAN, b(True), True),
        (BOOLEAN, b(False), False),
        (CODE, s("draft"), "draft"),
        (CODE, s("черновик"), "черновик"),
        (TEXT, s(""), ""),
        (FEE, s("12.50"), "12.5"),
        (FEE, s("+0012.00"), "12"),
        (FEE, s("-0.0"), "0"),
        (FEE, s("-1.05"), "-1.05"),
        (FEE, i(7), "7"),
        (DATE, s("2026-02-28"), "2026-02-28"),
        (DATE, ts("2026-02-28"), "2026-02-28"),
        (TIMESTAMP, s("2026-01-01T10:20:30.500"), "2026-01-01T10:20:30.5"),
        (TIMESTAMP, ts("2026-01-01T10:20:30"), "2026-01-01T10:20:30"),
        (TIMESTAMP_TZ, s("2026-01-01T03:00:00+03:00"), "2026-01-01T00:00:00Z"),
        (TIMESTAMP_TZ, s("2025-12-31T23:30:00.000001-01:00"), "2026-01-01T00:30:00.000001Z"),
        (UUID, s("3f2504e0-4f89-41d3-9a0c-0305e82c3301"), "3f2504e0-4f89-41d3-9a0c-0305e82c3301"),
    ],
)
def test_valid_value_is_normalized(column_type: ColumnType, raw: RawValue, form: object) -> None:
    value = _value(column_type, raw)

    assert value.value == form
    assert type(value.value) is type(form)


@pytest.mark.parametrize(
    "column_type", [INTEGER, BOOLEAN, CODE, TEXT, FEE, DATE, TIMESTAMP, TIMESTAMP_TZ, UUID]
)
def test_null_is_null_of_any_type(column_type: ColumnType) -> None:
    assert _value(column_type, NULL).is_null()


def test_decimal_values_equal_by_form() -> None:
    assert _value(FEE, s("1.50")) == _value(FEE, s("1.5"))


def test_same_moment_with_different_offsets_is_one_value() -> None:
    moscow = _value(TIMESTAMP_TZ, s("2026-01-01T03:00:00+03:00"))
    utc = _value(TIMESTAMP_TZ, s("2026-01-01T00:00:00Z"))

    assert moscow == utc


@pytest.mark.parametrize(
    ("column_type", "raw", "code"),
    [
        (INTEGER, s("10"), "invalid_value"),
        (INTEGER, f("10.0"), "invalid_value"),
        (INTEGER, b(True), "invalid_value"),
        (INTEGER, i(3_000_000_000), "value_out_of_range"),
        (INTEGER, i(-(2**31) - 1), "value_out_of_range"),
        (BIGINT, i(2**63), "value_out_of_range"),
        (BOOLEAN, s("true"), "invalid_value"),
        (BOOLEAN, i(1), "invalid_value"),
        (CODE, s("cancelled_by_user"), "value_out_of_range"),
        (CODE, i(404), "invalid_value"),
        (CODE, b(True), "invalid_value"),
        (TEXT, f("1.5"), "invalid_value"),
        (FEE, f("12.5"), "invalid_value"),
        (FEE, s("1.255"), "value_out_of_range"),
        (FEE, s("12345678901"), "value_out_of_range"),
        (FEE, s("12,50"), "invalid_value"),
        (FEE, s(".5"), "invalid_value"),
        (DATE, s("2026-02-30"), "invalid_value"),
        (DATE, s("2026-2-3"), "invalid_value"),
        (DATE, i(20260101), "invalid_value"),
        (TIMESTAMP, s("2026-01-01T00:00:00Z"), "invalid_value"),
        (TIMESTAMP, ts("2026-01-01 00:00:00"), "invalid_value"),
        (TIMESTAMP, s("2026-01-01T24:00:00"), "invalid_value"),
        (TIMESTAMP, s("2026-01-01T00:00:00.1234567"), "invalid_value"),
        (TIMESTAMP_TZ, s("2026-01-01T00:00:00"), "invalid_value"),
        (TIMESTAMP_TZ, s("2026-01-01T00:00:00+03:60"), "invalid_value"),
        (UUID, s("3F2504E0-4F89-41D3-9A0C-0305E82C3301"), "invalid_value"),
        (UUID, s("3f2504e04f8941d39a0c0305e82c3301"), "invalid_value"),
        (UUID, RawValue(ScalarKind.OTHER, "список"), "invalid_value"),
    ],
)
def test_wrong_value(column_type: ColumnType, raw: RawValue, code: str) -> None:
    assert _code(column_type, raw) == code


def test_number_in_string_column_suggests_quotes() -> None:
    violation = SeedValueFactory().create(CODE, i(404))

    assert isinstance(violation, Violation)
    assert "кавычки" in violation.message
    assert "'404'" in violation.message
