"""Шаблоны беклогов: приёмка плагином и отсутствие текста чужой ветки в порождённом беклоге.

`backlog check-template` проверяет структуру, но не видит текст, попавший в задачу из выключенной
ветки условного блока. Плагин `formular` 1.3.0 оставляет такой текст, если блок вложен в другой
блок, поэтому шаблоны проекта обходятся без вложенных блоков, а тест это закрепляет.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.operation.backlogs import PROJECT_ROOT, backlog_cli

TEMPLATES = PROJECT_ROOT / "templates"
VARIANTS = [(auto, first) for auto in (True, False) for first in (True, False)]


def _flag(name: str, on: bool) -> list[str]:
    return ["--flag" if on else "--no-flag", name]


def _attempt_backlog(root: Path, auto: bool, first: bool) -> str:
    subject = f"v-{int(auto)}-{int(first)}"
    subprocess.run(
        [
            backlog_cli(),
            "generate",
            "--operation", "forge-apply",
            "--subject", subject,
            "--value", "parent=backlog/forge-model/20261017-153000/tasks.md",
            "--value", "attempt=1",
            "--value", "trail=backlog/forge-model/20261017-153000/attempt-1",
            *_flag("first-attempt", first),
            *_flag("auto", auto),
            "--root", str(root),
            "--templates", str(TEMPLATES),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    return (root / "forge-apply" / subject / "tasks.md").read_text(encoding="utf-8")


def _tasks(text: str) -> str:
    """Текст беклога после фронтматтера: задачи и преамбула."""
    return text.split("\n---\n", 1)[1]


@pytest.mark.parametrize("template", ["forge-model.md", "forge-apply.md"])
def test_template_is_accepted(template: str) -> None:
    result = subprocess.run(
        [backlog_cli(), "check-template", str(TEMPLATES / template)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "расхождений 0" in result.stdout


@pytest.mark.parametrize(("auto", "first"), VARIANTS)
def test_attempt_backlog_has_only_its_branch(tmp_path: Path, auto: bool, first: bool) -> None:
    tasks = _tasks(_attempt_backlog(tmp_path, auto, first))
    section = tasks.split("## 2. Модель данных", 1)[1].split("- [ ] 2.2", 1)[0]

    assert len(re.findall(r"^- \[ \] 2\.1 ", section, re.M)) == 1
    assert section.lstrip().startswith("- [ ] 2.1 "), "текст до задачи 2.1 — из чужой ветки"
    assert ("gate.model" in section) is auto
    assert ("confirmed.model" in section) is not auto
    assert ("как понято намерение" in section) is first
    assert ("расхождения предыдущей попытки" in section) is not first


@pytest.mark.parametrize(("auto", "first"), VARIANTS)
def test_attempt_backlog_names_its_mode_only(tmp_path: Path, auto: bool, first: bool) -> None:
    tasks = _tasks(_attempt_backlog(tmp_path, auto, first))

    assert ("Автоматический гейт" in tasks) is auto
    assert ("**Стоп-знак.**" in tasks) is not auto
    assert "--operation backlog/forge-model/20261017-153000/tasks.md --out" in tasks
