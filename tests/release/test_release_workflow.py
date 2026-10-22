"""Релизный сценарий `.github/workflows/release.yml`: структура и логика повышения номера.

Логика проверяется на тексте сценария: тест берёт скрипт шага разбора версии и исполняет его
через `sh` с временными `VERSION` и `GITHUB_OUTPUT` — ровно тот код, что работает в GitHub.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def _workflow() -> dict[Any, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _steps() -> list[dict[str, Any]]:
    steps = _workflow()["jobs"]["release"]["steps"]
    assert isinstance(steps, list)
    return steps


def _step_index(fragment: str) -> int:
    """Номер первого шага, скрипт которого содержит фрагмент."""
    return next(index for index, step in enumerate(_steps()) if fragment in step.get("run", ""))


def _bump(tmp_path: Path, version: str, bump: str) -> tuple[subprocess.CompletedProcess[str], str]:
    script = next(step["run"] for step in _steps() if step.get("id") == "version")
    (tmp_path / "VERSION").write_text(version)
    output = tmp_path / "github_output"
    output.write_text("")
    result = subprocess.run(
        ["sh", "-e", "-c", script],
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "BUMP": bump, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
        check=False,
    )
    return result, output.read_text()


# --- Структура -------------------------------------------------------------------------------


def test_only_manual_trigger() -> None:
    # PyYAML читает ключ `on` по YAML 1.1 как логическое True
    triggers = _workflow()[True]

    assert list(triggers) == ["workflow_dispatch"]


def test_single_input_is_bump_level() -> None:
    inputs = _workflow()[True]["workflow_dispatch"]["inputs"]

    assert list(inputs) == ["bump"]
    assert inputs["bump"]["type"] == "choice"
    assert inputs["bump"]["options"] == ["patch", "minor", "major"]


def test_only_contents_write_permission() -> None:
    assert _workflow()["permissions"] == {"contents": "write"}


def test_main_branch_gate_comes_first() -> None:
    assert "refs/heads/main" in _steps()[0]["run"]


def test_release_is_published_after_tag_push() -> None:
    tag_push = _step_index('git push origin "v$NEXT"')
    release = _step_index("gh release create")

    assert _step_index("git push origin HEAD") == tag_push
    assert tag_push < release
    assert "--verify-tag" in _steps()[release]["run"]


def test_release_commit_changes_only_version() -> None:
    script = _steps()[_step_index("git commit")]["run"]

    assert "git add VERSION\n" in script
    assert 'git commit -m "Релиз v$NEXT"' in script
    assert 'git tag -a "v$NEXT"' in script


def test_input_is_passed_through_env() -> None:
    step = next(step for step in _steps() if step.get("id") == "version")

    assert "${{" not in step["run"]
    assert step["env"]["BUMP"] == "${{ inputs.bump }}"


# --- Повышение номера ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "bump", "expected"),
    [
        ("0.1.0", "minor", "0.2.0"),
        ("1.4.3", "major", "2.0.0"),
        ("1.4.3", "patch", "1.4.4"),
    ],
)
def test_bump(tmp_path: Path, current: str, bump: str, expected: str) -> None:
    result, output = _bump(tmp_path, f"{current}\n", bump)

    assert result.returncode == 0, result.stderr
    assert output.splitlines() == [f"current={current}", f"next={expected}"]


def test_incomplete_version_stops_release(tmp_path: Path) -> None:
    result, output = _bump(tmp_path, "0.2\n", "minor")

    assert result.returncode != 0
    assert "«0.2»" in result.stderr
    assert output == ""
