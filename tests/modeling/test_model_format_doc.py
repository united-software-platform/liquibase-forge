"""Пример из `docs/model-format.md` совпадает с фикстурой и проходит проверку."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from forge.modeling.application.validate_model.input import ValidateModelInput
from forge.modeling.application.validate_model.use_case import ValidateModelUseCase
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs" / "model-format.md"
FIXTURE = ROOT / "tests" / "fixtures" / "model" / "example.yaml"


def _example_block() -> str:
    text = DOCUMENT.read_text(encoding="utf-8")
    section = text.split("\n## Пример\n", 1)[1].split("\n## ", 1)[0]
    match = re.search(r"```yaml\n(.*?)```", section, re.S)
    assert match, "в разделе «Пример» нет блока yaml"
    return match.group(1)


def test_document_example_matches_fixture() -> None:
    assert _example_block() == FIXTURE.read_text(encoding="utf-8")


def test_fixture_example_is_valid() -> None:
    use_case = ValidateModelUseCase(YamlModelDraftReader(), DataModelFactory())

    output = use_case.execute(ValidateModelInput(str(FIXTURE)))

    assert (output.valid, output.violations) == (True, ())


@pytest.mark.parametrize("section", ["Генерация значения", "Перечень значений"])
def test_section_example_is_valid(section: str, tmp_path: Path) -> None:
    text = DOCUMENT.read_text(encoding="utf-8")
    body = text.split(f"\n## {section}\n", 1)[1].split("\n## ", 1)[0]
    match = re.search(r"```yaml\n(.*?)```", body, re.S)
    assert match, f"в разделе «{section}» нет блока yaml"
    model = tmp_path / "model.yaml"
    model.write_text(match.group(1), encoding="utf-8")
    use_case = ValidateModelUseCase(YamlModelDraftReader(), DataModelFactory())

    output = use_case.execute(ValidateModelInput(str(model)))

    assert (output.valid, output.violations) == (True, ())
