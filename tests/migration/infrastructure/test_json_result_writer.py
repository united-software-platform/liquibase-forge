"""Запись файла результата: JSON целиком, каталог создаётся, временный файл не остаётся."""

from __future__ import annotations

import json
from pathlib import Path

from forge.migration.infrastructure.json_result_writer import JsonResultWriter


def test_document_is_written_atomically(tmp_path: Path) -> None:
    path = tmp_path / "attempt-1" / "rollback.json"

    JsonResultWriter().write(str(path), {"verified": True, "причина": None})

    assert json.loads(path.read_text(encoding="utf-8")) == {"verified": True, "причина": None}
    assert [p.name for p in path.parent.iterdir()] == ["rollback.json"]
