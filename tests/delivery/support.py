"""Общие средства тестов поставки: корень репозитория и разбор `delivery.txt`."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DELIVERY_LIST = ROOT / "delivery.txt"
BLOCKS_DIR = ROOT / "install" / "blocks"

BEGIN_MARKER = "# >>> liquibase-forge"
END_MARKER = "# <<< liquibase-forge"


def delivery_entries() -> list[tuple[str, str]]:
    """Пары `источник → цель` перечня; строка без стрелки кладёт источник по тому же пути."""
    entries = []
    for raw in DELIVERY_LIST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        source, _, target = (part.strip() for part in line.partition("->"))
        entries.append((source, target or source))
    return entries


def marked_block(text: str) -> str:
    """Текст между маркерами forge без самих маркеров; ровно один блок на файл."""
    lines = text.splitlines(keepends=True)
    begins = [index for index, line in enumerate(lines) if line.strip() == BEGIN_MARKER]
    ends = [index for index, line in enumerate(lines) if line.strip() == END_MARKER]
    assert len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0], "нет пары маркеров forge"
    return "".join(lines[begins[0] + 1 : ends[0]])
