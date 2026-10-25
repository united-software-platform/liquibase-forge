"""Сценарий проверки seed на фейках: порядок нарушений, повторный ответ, загрузка модели."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from forge.modeling.application.load_model.input import LoadModelInput
from forge.modeling.application.load_model.output import LoadModelOutput
from forge.modeling.application.load_model.use_case import InvalidModelError
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.draft import ColumnDraft
from forge.modeling.domain.violation import Violation
from forge.seeding.application.seed_reading import SeedReading
from forge.seeding.application.validate_seed.input import ValidateSeedInput
from forge.seeding.application.validate_seed.use_case import ValidateSeedUseCase
from forge.seeding.domain.draft import SeedDraft
from forge.seeding.domain.factory import SeedFactory
from tests.seeding.support import ORDER_STATUS, model, row, s, seed, table

MODEL = model(ORDER_STATUS, table("token", ColumnDraft("id", "uuid"), key=("id",)))


@dataclass
class FakeModels:
    data_model: DataModel = MODEL
    error: Exception | None = None
    calls: list[LoadModelInput] = field(default_factory=list)

    def execute(self, input: LoadModelInput) -> LoadModelOutput:
        self.calls.append(input)
        if self.error is not None:
            raise self.error
        return LoadModelOutput(self.data_model, found=True)


@dataclass
class FakeReader:
    reading: SeedReading
    calls: list[str] = field(default_factory=list)

    def read(self, path: str) -> SeedReading:
        self.calls.append(path)
        return self.reading


def _use_case(reading: SeedReading, models: FakeModels | None = None) -> ValidateSeedUseCase:
    return ValidateSeedUseCase(models or FakeModels(), FakeReader(reading), SeedFactory())


def _input() -> ValidateSeedInput:
    return ValidateSeedInput("seed.yaml", "model.yaml")


def test_valid_seed() -> None:
    reading = SeedReading(seed(("order_status", (row(code=s("new"), title=s("Новый")),))), ())

    output = _use_case(reading).execute(_input())

    assert (output.seed_path, output.model_path, output.valid, output.violations) == (
        "seed.yaml",
        "model.yaml",
        True,
        (),
    )


def test_violations_of_different_tables_in_document_order() -> None:
    draft = seed(
        ("order_status", (row(title=s("Новый")),)),
        ("token", (row(id=s("3F2504E0-4F89-41D3-9A0C-0305E82C3301")),)),
    )

    output = _use_case(SeedReading(draft, ())).execute(_input())

    assert output.valid is False
    assert [(v.path, v.code) for v in output.violations] == [
        ("tables[0].rows[0].code", "null_value"),
        ("tables[1].rows[0].id", "invalid_value"),
    ]


def test_structure_violations_come_first() -> None:
    draft = seed(("order_state", ()))
    structure = Violation("tables[1].rows[0]", "wrong_kind", "ожидалось: отображение")

    output = _use_case(SeedReading(draft, (structure,))).execute(_input())

    assert [(v.path, v.code) for v in output.violations] == [
        ("tables[1].rows[0]", "wrong_kind"),
        ("tables[0].name", "unknown_table"),
    ]


def test_repeated_check_gives_equal_answer() -> None:
    draft = seed(("order_status", (row(code=s("a")), row(code=s("a"), title=s("x")))))
    use_case = _use_case(SeedReading(draft, ()))

    assert use_case.execute(_input()) == use_case.execute(_input())


def test_model_is_loaded_with_missing_as_empty_flag() -> None:
    models = FakeModels()
    use_case = _use_case(SeedReading(SeedDraft(()), ()), models)

    use_case.execute(ValidateSeedInput("seed.yaml", "db/model.yaml", missing_model_as_empty=True))

    assert models.calls == [LoadModelInput("db/model.yaml", missing_as_empty=True)]


def test_invalid_model_stops_before_seed() -> None:
    models = FakeModels(error=InvalidModelError("model.yaml", ()))
    reader = FakeReader(SeedReading(SeedDraft(()), ()))
    use_case = ValidateSeedUseCase(models, reader, SeedFactory())

    with pytest.raises(InvalidModelError):
        use_case.execute(_input())

    assert reader.calls == []
