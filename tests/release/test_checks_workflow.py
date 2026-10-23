"""Workflow проверок `.github/workflows/checks.yml`: триггеры, права и совпадение с CONTRIBUTING.md.

Перечень проверок живёт в двух местах — в разделе «Проверки» `CONTRIBUTING.md` для локального
прогона и в шагах workflow для CI. Тест сравнивает их, чтобы новая проверка не попала только
в одно место.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "checks.yml"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"

# Установка зависимостей нужна только CI: локально окружение uv уже есть
CI_ONLY = {"uv sync --frozen"}


def _workflow() -> dict[Any, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _steps() -> list[dict[str, Any]]:
    steps = _workflow()["jobs"]["checks"]["steps"]
    assert isinstance(steps, list)
    return steps


def _workflow_commands() -> set[str]:
    return {step["run"].strip() for step in _steps() if "run" in step} - CI_ONLY


def _contributing_commands() -> set[str]:
    """Команды блока `bash` раздела «Проверки» без комментариев.

    `uv run pytest <каталог>` — частный случай полного `uv run pytest` и им покрыт.
    """
    text = CONTRIBUTING.read_text(encoding="utf-8")
    section = text.split("\n## Проверки\n", 1)[1].split("\n## ", 1)[0]
    block = re.search(r"```bash\n(.*?)```", section, re.DOTALL)
    assert block is not None, "в разделе «Проверки» нет блока bash"
    commands = {line.split("#", 1)[0].strip() for line in block.group(1).splitlines()}
    return {
        "uv run pytest" if command.startswith("uv run pytest ") else command
        for command in commands
        if command
    }


# --- Триггеры и права ------------------------------------------------------------------------


def test_triggers_are_pr_and_push_to_main_and_call() -> None:
    # PyYAML читает ключ `on` по YAML 1.1 как логическое True
    triggers = _workflow()[True]

    assert set(triggers) == {"pull_request", "push", "workflow_call"}
    assert triggers["pull_request"]["branches"] == ["main"]
    assert triggers["push"]["branches"] == ["main"]


def test_only_read_permission() -> None:
    assert _workflow()["permissions"] == {"contents": "read"}
    assert "permissions" not in _workflow()["jobs"]["checks"]


# --- Состав проверок -------------------------------------------------------------------------


def test_commands_match_contributing() -> None:
    assert _workflow_commands() == _contributing_commands()


def test_dependencies_installed_from_lock() -> None:
    commands = [step["run"].strip() for step in _steps() if "run" in step]

    assert commands[0] == "uv sync --frozen"


def test_no_check_is_allowed_to_fail() -> None:
    job = _workflow()["jobs"]["checks"]

    assert "continue-on-error" not in job
    assert all("continue-on-error" not in step for step in _steps())


def test_environment_for_skipped_tests_is_not_set() -> None:
    env_keys = {key for step in _steps() for key in step.get("env", {})}
    env_keys |= set(_workflow().get("env", {})) | set(_workflow()["jobs"]["checks"].get("env", {}))

    assert not env_keys & {"FORGE_TEST_DB_HOST", "AGENT_RUNNER_URL", "AGENT_RUNNER_TOKEN"}


def test_makefile_check_uses_norm() -> None:
    assert "sh tools/make-lint/check.sh" in _workflow_commands()
    assert not any("--max-lines" in command for command in _workflow_commands())
