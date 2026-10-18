"""Беклоги операции для тестов Операции: фикстура плагина и порождение по текущему шаблону."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGACY = PROJECT_ROOT / "tests" / "fixtures" / "operation" / "forge-model-1.0.0.md"
STAMP = "20261017-153000"


def backlog_cli() -> str:
    """Путь к `backlog` плагина `formular`; без плагина тест пропускается."""
    found = shutil.which("backlog") or next(
        iter(
            sorted(
                glob.glob(
                    os.path.expanduser("~/.claude/plugins/cache/formular/backlog/*/bin/backlog")
                ),
                reverse=True,
            )
        ),
        None,
    )
    if found is None:
        pytest.skip("плагин backlog@formular не установлен: команда backlog не найдена")
    return found


def generate(root: Path, stamp: str = STAMP, auto: bool = True) -> Path:
    """Породить беклог `forge-model` по текущему шаблону проекта в корне следа `root`."""
    subprocess.run(
        [
            backlog_cli(),
            "generate",
            "--operation", "forge-model",
            "--subject", stamp,
            "--value", "intent=Справочник клиентов: id, email, имя",
            "--flag" if auto else "--no-flag", "auto",
            "--root", str(root),
            "--templates", str(PROJECT_ROOT / "templates"),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    return root / "forge-model" / stamp / "tasks.md"


def legacy(root: Path, stamp: str = STAMP) -> Path:
    """Беклог по шаблону 1.0.0 в корне следа `root`: без `trail` и `stop_reason`."""
    path = root / "forge-model" / stamp / "tasks.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        LEGACY.read_text(encoding="utf-8").replace("20261017-153000", stamp), encoding="utf-8"
    )
    return path


def set_values(path: Path, **values: str) -> None:
    """Заменить значения верхнего уровня и попыток фронтматтера, как это делает исполнение."""
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        if "__" in key:
            block, attempt = key.split("__")
            text = _replace_attempt(text, block, attempt, value)
        else:
            text = "\n".join(
                f"{key}: {value}" if line.startswith(f"{key}:") else line
                for line in text.split("\n")
            )
    path.write_text(text, encoding="utf-8")


def _replace_attempt(text: str, block: str, attempt: str, value: str) -> str:
    lines = text.split("\n")
    inside = False
    for index, line in enumerate(lines):
        if line == f"{block}:":
            inside = True
            continue
        if inside and not line.startswith("  "):
            inside = False
        if inside and line.startswith(f"  {attempt}:"):
            lines[index] = f"  {attempt}: {value}"
            break
    return "\n".join(lines)
