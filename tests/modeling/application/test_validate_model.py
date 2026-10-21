"""Сценарий проверки модели: объединение структурных нарушений и нарушений инвариантов."""

from __future__ import annotations

import pytest

from forge.modeling.application.model_reading import DraftReading, ModelUnreadableError
from forge.modeling.application.validate_model.input import ValidateModelInput
from forge.modeling.application.validate_model.output import ViolationView
from forge.modeling.application.validate_model.use_case import ValidateModelUseCase
from forge.modeling.domain.draft import ColumnDraft, DataModelDraft, TableDraft
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.domain.violation import Violation
from tests.modeling.example import EXAMPLE

STRUCTURAL = Violation("tables[0].columns[0].default", "unknown_field", "поле default")
INVALID_TABLE = TableDraft(1, "invoice", (ColumnDraft("id", "bigint"),), ("id", "code"))


class _StubReader:
    """Подставная реализация контракта чтения: отдаёт заранее заданный результат."""

    def __init__(self, reading: DraftReading | None = None) -> None:
        self._reading = reading
        self.paths: list[str] = []

    def read(self, path: str) -> DraftReading:
        self.paths.append(path)
        if self._reading is None:
            raise ModelUnreadableError(path, "файла нет")
        return self._reading


def test_valid_model() -> None:
    output = ValidateModelUseCase(
        _StubReader(DraftReading(EXAMPLE, ())), DataModelFactory()
    ).execute(ValidateModelInput("db/model.yaml"))

    assert output.model_path == "db/model.yaml"
    assert output.valid is True
    assert output.violations == ()


def test_only_structural_violations() -> None:
    reading = DraftReading(DataModelDraft(()), (STRUCTURAL,))

    output = ValidateModelUseCase(_StubReader(reading), DataModelFactory()).execute(
        ValidateModelInput("m.yaml")
    )

    assert output.valid is False
    assert output.violations == (
        ViolationView("tables[0].columns[0].default", "unknown_field", "поле default"),
    )


def test_only_invariant_violations() -> None:
    reading = DraftReading(DataModelDraft((INVALID_TABLE,)), ())

    output = ValidateModelUseCase(_StubReader(reading), DataModelFactory()).execute(
        ValidateModelInput("m.yaml")
    )

    assert output.valid is False
    assert [(v.path, v.code) for v in output.violations] == [
        ("tables[1].primary_key[1]", "primary_key_unknown_column")
    ]


def test_structural_violations_come_before_invariant_violations() -> None:
    reading = DraftReading(DataModelDraft((INVALID_TABLE,)), (STRUCTURAL,))

    output = ValidateModelUseCase(_StubReader(reading), DataModelFactory()).execute(
        ValidateModelInput("m.yaml")
    )

    assert [(v.path, v.code) for v in output.violations] == [
        ("tables[0].columns[0].default", "unknown_field"),
        ("tables[1].primary_key[1]", "primary_key_unknown_column"),
    ]


def test_unreadable_model_is_not_caught() -> None:
    with pytest.raises(ModelUnreadableError):
        ValidateModelUseCase(_StubReader(None), DataModelFactory()).execute(
            ValidateModelInput("missing.yaml")
        )
