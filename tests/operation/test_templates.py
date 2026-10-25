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
import yaml

from tests.operation.backlogs import PROJECT_ROOT, backlog_cli, generate

TEMPLATES = PROJECT_ROOT / "templates"
VARIANTS = [
    (auto, first, drop)
    for auto in (True, False)
    for first in (True, False)
    for drop in (True, False)
]


def _flag(name: str, on: bool) -> list[str]:
    return ["--flag" if on else "--no-flag", name]


def _attempt_backlog(root: Path, auto: bool, first: bool, drop: bool) -> str:
    subject = f"v-{int(auto)}-{int(first)}-{int(drop)}"
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
            *_flag("allow-drop", drop),
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


@pytest.mark.parametrize(("auto", "first", "drop"), VARIANTS)
def test_attempt_backlog_has_only_its_branch(
    tmp_path: Path, auto: bool, first: bool, drop: bool
) -> None:
    tasks = _tasks(_attempt_backlog(tmp_path, auto, first, drop))
    section = tasks.split("## 2. Модель данных", 1)[1].split("- [ ] 2.2", 1)[0]

    assert len(re.findall(r"^- \[ \] 2\.1 ", section, re.M)) == 1
    assert section.lstrip().startswith("- [ ] 2.1 "), "текст до задачи 2.1 — из чужой ветки"
    assert ("gate.model" in section) is auto
    assert ("confirmed.model" in section) is not auto
    assert ("как понято намерение" in section) is first
    assert ("расхождения предыдущей попытки" in section) is not first


@pytest.mark.parametrize(("auto", "first", "drop"), VARIANTS)
def test_attempt_backlog_names_its_mode_only(
    tmp_path: Path, auto: bool, first: bool, drop: bool
) -> None:
    tasks = _tasks(_attempt_backlog(tmp_path, auto, first, drop))

    assert ("Автоматический гейт" in tasks) is auto
    assert ("**Стоп-знак.**" in tasks) is not auto
    assert "--operation backlog/forge-model/20261017-153000/tasks.md --out" in tasks


@pytest.mark.parametrize(("auto", "first", "drop"), VARIANTS)
def test_attempt_backlog_records_drop_consent(
    tmp_path: Path, auto: bool, first: bool, drop: bool
) -> None:
    frontmatter = _attempt_backlog(tmp_path, auto, first, drop).split("\n---\n")[0]

    assert frontmatter.count("allow_drop:") == 1
    assert f"allow_drop: {'true' if drop else 'false'}" in frontmatter


@pytest.mark.parametrize("drop", [True, False])
def test_attempts_take_consent_from_operation_frontmatter(tmp_path: Path, drop: bool) -> None:
    text = generate(tmp_path, allow_drop=drop).read_text(encoding="utf-8")
    frontmatter, tasks = text.split("\n---\n", 1)

    assert f"allow_drop: {'true' if drop else 'false'}" in frontmatter
    # Флаг попытки не вшит при порождении: согласие, данное при продолжении, дойдёт до попыток
    rule = "`--flag allow-drop` при `allow_drop: true` во фронтматтере этого беклога"
    assert tasks.count(rule) == 3


SEED_PAIRS = [("forge-model.md", "forge-seed.md"), ("forge-apply.md", "forge-seed-apply.md")]
# Отличия пар шаблонов в командах задач: всё прочее у модели и seed общее
SEED_COMMANDS = {
    "forge validate": "forge validate-seed",
    "forge generate": "forge generate-seed",
    "forge reconcile": "forge reconcile-seed",
}
_TASK = re.compile(r"^- \[ \] (\d+\.\d+) ", re.M)
_COMMAND = re.compile(r"`((?:forge|backlog) [a-z-]+)")


def _task_commands(template: str) -> dict[str, list[str]]:
    """Команды каждой задачи шаблона по номеру задачи, в порядке текста и без повторов."""
    text = (TEMPLATES / template).read_text(encoding="utf-8").split("## 1. Предусловия", 1)[1]
    text = text.split("## Версионирование", 1)[0]
    starts = [(m.group(1), m.start()) for m in _TASK.finditer(text)]
    commands: dict[str, list[str]] = {}
    for index, (number, start) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        found = commands.setdefault(number, [])
        for command in _COMMAND.findall(text[start:end]):
            if command not in found:
                found.append(command)
    return commands


@pytest.mark.parametrize("template", ["forge-seed.md", "forge-seed-apply.md"])
def test_seed_template_is_accepted(template: str) -> None:
    result = subprocess.run(
        [backlog_cli(), "check-template", str(TEMPLATES / template)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "расхождений 0" in result.stdout


@pytest.mark.parametrize(("model", "seed"), SEED_PAIRS)
def test_seed_templates_share_tasks_with_model_templates(model: str, seed: str) -> None:
    expected = {
        number: [SEED_COMMANDS.get(command, command) for command in commands]
        for number, commands in _task_commands(model).items()
    }

    assert _task_commands(seed) == expected


def _seed_backlog(root: Path, sources: str = "[]", auto: bool = True) -> str:
    subprocess.run(
        [
            backlog_cli(),
            "generate",
            "--operation", "forge-seed",
            "--subject", "20261025-101500",
            "--value", "intent=Статусы заказа",
            "--value", f"sources={sources}",
            *_flag("auto", auto),
            "--no-flag", "allow-drop",
            "--root", str(root),
            "--templates", str(TEMPLATES),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    return (root / "forge-seed" / "20261025-101500" / "tasks.md").read_text(encoding="utf-8")


def _seed_attempt_backlog(root: Path, auto: bool, first: bool, drop: bool) -> str:
    subject = f"v-{int(auto)}-{int(first)}-{int(drop)}"
    subprocess.run(
        [
            backlog_cli(),
            "generate",
            "--operation", "forge-seed-apply",
            "--subject", subject,
            "--value", "parent=backlog/forge-seed/20261025-101500/tasks.md",
            "--value", "attempt=1",
            "--value", "trail=backlog/forge-seed/20261025-101500/attempt-1",
            *_flag("first-attempt", first),
            *_flag("auto", auto),
            *_flag("allow-drop", drop),
            "--root", str(root),
            "--templates", str(TEMPLATES),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    return (root / "forge-seed-apply" / subject / "tasks.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("auto", [True, False])
def test_seed_operation_backlog_names_kind_and_sources(tmp_path: Path, auto: bool) -> None:
    text = _seed_backlog(tmp_path, '["data/statuses.csv"]', auto)
    frontmatter = yaml.safe_load(text.split("\n---\n", 1)[0].split("---\n", 1)[1])

    assert (frontmatter["kind"], frontmatter["sources"]) == ("seed", ["data/statuses.csv"])
    assert (frontmatter["mode"], frontmatter["allow_drop"]) == (
        "auto" if auto else "interactive",
        False,
    )
    assert "backlog/forge-seed-apply/20261025-101500-1/tasks.md" in _tasks(text)


@pytest.mark.parametrize(("auto", "first", "drop"), VARIANTS)
def test_seed_attempt_backlog_leaves_accepted_paths_to_cli(
    tmp_path: Path, auto: bool, first: bool, drop: bool
) -> None:
    text = _seed_attempt_backlog(tmp_path, auto, first, drop)
    tasks = _tasks(text)

    assert "db/seed.yaml" not in text and "db/model.yaml" not in text
    assert "--accepted-seed" not in tasks and "--model" not in tasks
    assert "`forge generate-seed --seed" in tasks and "`forge reconcile-seed --seed" in tasks
    assert ("Автоматический гейт" in tasks) is auto
    assert ("deleted_rows" in tasks) is not auto
    section = tasks.split("## 2. Seed", 1)[1].split("- [ ] 2.2", 1)[0]
    assert section.lstrip().startswith("- [ ] 2.1 "), "текст до задачи 2.1 — из чужой ветки"
    assert ("как понято намерение" in section) is first
    assert ("расхождения предыдущей попытки" in section) is not first
