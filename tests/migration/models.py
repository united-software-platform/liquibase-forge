"""Модели для тестов Миграции: строятся из текста YAML тем же разборщиком и фабрикой."""

from __future__ import annotations

from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.infrastructure.yaml_reader import parse_model


def model(tables: str = "") -> DataModel:
    """Модель из списка таблиц в YAML; пустая строка — пустая модель."""
    text = "version: 1\ntables:\n" + tables if tables else "version: 1\ntables: []\n"
    reading = parse_model(text)
    assert reading.violations == (), reading.violations
    return DataModelFactory().create(reading.draft)


CUSTOMER = """
  - name: customer
    columns:
      - {name: id, type: uuid}
      - {name: email, type: string, length: 255, nullable: false}
    primary_key: [id]
"""

INVOICE = """
  - name: invoice
    columns:
      - {name: number, type: bigint}
      - {name: total, type: decimal, precision: 12, scale: 2}
    primary_key: [number]
"""
