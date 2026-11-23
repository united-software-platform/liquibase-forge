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
PLUGIN = PROJECT_ROOT / "plugins" / "forge-plugin"
TEMPLATES = PLUGIN / "skills" / "forge" / "templates"
# Каталоги кеша плагина backlog в харнесах: CLI из кеша узнаёт каталог поставки
# только через BACKLOG_HOME
CACHES = (
    "~/.zcode/cli/plugins/cache/formular/backlog/*",
    "~/.claude/plugins/cache/formular/backlog/*",
)


def _version_key(path: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in Path(path).name.split("."))
    except ValueError:
        return ()


def _cached_delivery() -> str | None:
    """Каталог поставки плагина в кешах харнесов, наибольшая версия."""
    found = [
        path
        for pattern in CACHES
        for path in glob.glob(os.path.expanduser(pattern))
        if os.path.isfile(os.path.join(path, "bin", "backlog"))
    ]
    return max(found, key=_version_key) if found else None


def backlog_cli() -> str:
    """Путь к `backlog` плагина `formular`; без плагина тест пропускается.

    CLI из кеша харнеса не находит каталог поставки сам: `BACKLOG_HOME` задаётся здесь.
    """
    delivery = _cached_delivery()
    found = shutil.which("backlog") or (
        os.path.join(delivery, "bin", "backlog") if delivery else None
    )
    if found is None:
        pytest.skip("плагин backlog@formular не установлен: команда backlog не найдена")
    if delivery and not os.environ.get("BACKLOG_HOME"):
        os.environ["BACKLOG_HOME"] = delivery
    return found


def generate(root: Path, stamp: str = STAMP, auto: bool = True, allow_drop: bool = False) -> Path:
    """Породить беклог `forge-model` по текущему шаблону проекта в корне следа `root`."""
    subprocess.run(
        [
            backlog_cli(),
            "generate",
            "--operation", "forge-model",
            "--subject", stamp,
            "--value", "intent=Справочник клиентов: id, email, имя",
            "--flag" if auto else "--no-flag", "auto",
            "--flag" if allow_drop else "--no-flag", "allow-drop",
            "--root", str(root),
            "--templates",
            str(TEMPLATES),
            "--value",
            f"templates={TEMPLATES}",
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


def seed(root: Path, stamp: str = STAMP) -> Path:
    """Беклог операции seed в корне следа `root`: фронтматтер 1.0.0 с `kind: seed`."""
    path = root / "forge-seed" / stamp / "tasks.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = LEGACY.read_text(encoding="utf-8").replace("20261017-153000", stamp)
    text = text.replace("operation: forge-model\n", "operation: forge-seed\nkind: seed\n", 1)
    path.write_text(text.replace('intent: "Справочник', 'intent: "Статусы заказа', 1))
    return path


KINDS = {"model": legacy, "seed": seed}
"""Беклог операции каждого вида по фронтматтеру 1.0.0: для тестов, параметризованных по виду."""
ATTEMPT_TRAILS = {"model": "forge-apply", "seed": "forge-seed-apply"}
"""Каталог следа беклогов попыток каждого вида."""


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
