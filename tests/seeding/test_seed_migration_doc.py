"""Пример из `docs/seed-migration.md` совпадает с фикстурами и эталонным changelog данных."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.seeding.support import MIGRATION_EXAMPLE

DOCUMENT = Path(__file__).resolve().parents[2] / "docs" / "seed-migration.md"
FILES = ("model.yaml", "accepted.yaml", "attempt.yaml", "changelog.yaml")


def _example_blocks() -> list[str]:
    text = DOCUMENT.read_text(encoding="utf-8")
    section = text.split("\n## Пример\n", 1)[1].split("\n## ", 1)[0]
    blocks = re.findall(r"```yaml\n(.*?)```", section, re.S)
    assert len(blocks) == len(FILES), "в разделе «Пример» блоки модели, двух seed и changelog"
    return blocks


@pytest.mark.parametrize(("position", "name"), list(enumerate(FILES)))
def test_document_example_matches_fixture(position: int, name: str) -> None:
    assert _example_blocks()[position] == (MIGRATION_EXAMPLE / name).read_text(encoding="utf-8")


def test_document_links_lead_to_existing_files() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")

    for target in re.findall(r"\]\(\./([^)#]+)", text):
        assert (DOCUMENT.parent / target).is_file(), target
