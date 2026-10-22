"""Примеры changelog из `docs/migration.md` совпадают с тем, что строит запись changelog."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from forge.migration.domain.changelog import Changelog
from forge.migration.domain.model_diff import ModelDiff
from forge.migration.domain.stamp import OperationStamp
from forge.migration.infrastructure.liquibase_changelog import render_changelog
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.infrastructure.yaml_reader import parse_model

DOCUMENT = Path(__file__).resolve().parents[2] / "docs" / "migration.md"


def _blocks(heading: str) -> list[str]:
    text = DOCUMENT.read_text(encoding="utf-8")
    section = text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"```yaml\n(.*?)```", section, re.S)


def _model(text: str) -> DataModel:
    reading = parse_model(text)
    assert reading.violations == ()
    return DataModelFactory().create(reading.draft)


@pytest.mark.parametrize("heading", ["Changelog", "Удаления"])
def test_document_changelog_matches_rendering(heading: str) -> None:
    accepted, attempt, changelog = _blocks(heading)

    changes = ModelDiff().between(_model(accepted), _model(attempt))

    assert render_changelog(Changelog(OperationStamp("20261017-153000"), changes)) == changelog
