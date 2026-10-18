"""Сценарий загрузки модели: корректная, отсутствующая и некорректная модель."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.modeling.application.load_model.input import LoadModelInput
from forge.modeling.application.load_model.use_case import InvalidModelError, LoadModelUseCase
from forge.modeling.application.model_reading import ModelNotFoundError
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.domain.identifier import TableName
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader

EXAMPLE = Path(__file__).resolve().parents[2] / "fixtures" / "model" / "example.yaml"


def _use_case() -> LoadModelUseCase:
    return LoadModelUseCase(YamlModelDraftReader(), DataModelFactory())


def test_valid_model_is_loaded() -> None:
    output = _use_case().execute(LoadModelInput(str(EXAMPLE)))

    assert output.found is True
    assert output.model.has_table(TableName("invoice_line"))


def test_missing_file_as_empty_model(tmp_path: Path) -> None:
    output = _use_case().execute(
        LoadModelInput(str(tmp_path / "model.yaml"), missing_as_empty=True)
    )

    assert output.found is False
    assert output.model.tables == ()


def test_missing_file_without_flag_is_error(tmp_path: Path) -> None:
    with pytest.raises(ModelNotFoundError):
        _use_case().execute(LoadModelInput(str(tmp_path / "model.yaml")))


@pytest.mark.parametrize("missing_as_empty", [True, False])
def test_invalid_model_lists_all_violations(tmp_path: Path, missing_as_empty: bool) -> None:
    path = tmp_path / "model.yaml"
    path.write_text(
        "version: 1\nschema: x\ntables:\n"
        "  - {name: Customer, columns: [{name: id, type: bigint}], primary_key: [id]}\n",
        encoding="utf-8",
    )

    with pytest.raises(InvalidModelError) as caught:
        _use_case().execute(LoadModelInput(str(path), missing_as_empty=missing_as_empty))

    assert caught.value.path == str(path)
    assert [(v.path, v.code) for v in caught.value.violations] == [
        ("schema", "unknown_field"),
        ("tables[0].name", "invalid_identifier"),
    ]
