"""Расхождение — одно несоответствие, найденное сверкой."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Discrepancy:
    """Вид, объект (таблица, колонка либо `id` changeset), ожидаемое и фактическое значение."""

    kind: str
    table: str | None
    column: str | None
    changeset: str | None
    expected: str
    actual: str
    message: str
