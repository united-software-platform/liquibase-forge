"""Штамп операции: шаблон, путь принятого changelog, `id` changeset."""

from __future__ import annotations

import pytest

from forge.migration.domain.stamp import InvalidStampError, OperationStamp


def test_logical_file_path() -> None:
    assert (
        OperationStamp("20261017-153000").logical_file_path == "db/changelog/20261017-153000.yaml"
    )


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (1, "20261017-153000-01"),
        (9, "20261017-153000-09"),
        (10, "20261017-153000-10"),
        (100, "20261017-153000-100"),
    ],
)
def test_changeset_id(number: int, expected: str) -> None:
    assert OperationStamp("20261017-153000").changeset_id(number) == expected


def test_changeset_number_starts_with_one() -> None:
    with pytest.raises(ValueError):
        OperationStamp("20261017-153000").changeset_id(0)


@pytest.mark.parametrize(
    "value", ["", "20261017", "20261017-1530", "2026-10-17", "20261017-153000-1", "x0261017-153000"]
)
def test_invalid_stamp(value: str) -> None:
    with pytest.raises(InvalidStampError):
        OperationStamp(value)
