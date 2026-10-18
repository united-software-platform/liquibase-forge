"""Общее для интеграционных тестов Миграции: вызов CLI и запись модели."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from forge.cli.main import main

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAMP = "20261017-153000"


def forge(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    """Вызвать CLI и вернуть код и единственный JSON-объект вывода."""
    code = main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def write_model(path: Path, tables: str) -> Path:
    path.write_text(
        "version: 1\ntables:\n" + tables if tables else "version: 1\ntables: []\n", "utf-8"
    )
    return path
