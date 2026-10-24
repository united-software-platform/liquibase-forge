"""Пример из `docs/seed-format.md` совпадает с фикстурами и проходит проверку."""

from __future__ import annotations

import re
from pathlib import Path

from forge.modeling.application.load_model.use_case import LoadModelUseCase
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader
from forge.seeding.application.validate_seed.input import ValidateSeedInput
from forge.seeding.application.validate_seed.use_case import ValidateSeedUseCase
from forge.seeding.domain.factory import SeedFactory
from forge.seeding.infrastructure.yaml_reader import YamlSeedDraftReader

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs" / "seed-format.md"
FIXTURES = ROOT / "tests" / "fixtures" / "seed"


def _example_blocks() -> list[str]:
    text = DOCUMENT.read_text(encoding="utf-8")
    section = text.split("\n## Пример\n", 1)[1].split("\n## ", 1)[0]
    blocks = re.findall(r"```yaml\n(.*?)```", section, re.S)
    assert len(blocks) == 2, "в разделе «Пример» два блока yaml: модель и seed"
    return blocks


def test_document_model_matches_fixture() -> None:
    assert _example_blocks()[0] == (FIXTURES / "model.yaml").read_text(encoding="utf-8")


def test_document_seed_matches_fixture() -> None:
    assert _example_blocks()[1] == (FIXTURES / "example.yaml").read_text(encoding="utf-8")


def test_fixture_example_is_valid() -> None:
    use_case = ValidateSeedUseCase(
        LoadModelUseCase(YamlModelDraftReader(), DataModelFactory()),
        YamlSeedDraftReader(),
        SeedFactory(),
    )

    output = use_case.execute(
        ValidateSeedInput(str(FIXTURES / "example.yaml"), str(FIXTURES / "model.yaml"))
    )

    assert (output.valid, output.violations) == (True, ())
