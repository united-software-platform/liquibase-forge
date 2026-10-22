"""Отличия forge в файлах kit'а репозитория совпадают с фрагментами `install/blocks/`.

Установщик ставит в проект тексты фрагментов: расхождение с репозиторием ловится здесь,
а не в проекте пользователя.
"""

from __future__ import annotations

import pytest

from tests.delivery.support import BLOCKS_DIR, ROOT, marked_block

BLOCK_FILES = {
    "Makefile": "Makefile",
    "env.example": ".env.example",
    "docker-compose.yml": "docker-compose.yml",
    "runner.py": "tools/host-runner/runner.py",
    "gitignore": ".gitignore",
}


@pytest.mark.parametrize(("fragment", "path"), BLOCK_FILES.items())
def test_marked_block_matches_fragment(fragment: str, path: str) -> None:
    repository_block = marked_block((ROOT / path).read_text(encoding="utf-8"))

    assert repository_block == (BLOCKS_DIR / fragment).read_text(encoding="utf-8")


def test_every_fragment_has_a_file() -> None:
    assert sorted(item.name for item in BLOCKS_DIR.iterdir()) == sorted(BLOCK_FILES)
