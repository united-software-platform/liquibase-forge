"""Релизный сценарий `.github/workflows/release.yml`: структура и логика повышения номера.

Логика проверяется на тексте сценария: тест берёт скрипт шага разбора версии и исполняет его
через `sh` с временными `VERSION` и `GITHUB_OUTPUT` — ровно тот код, что работает в GitHub.
Гейт задач выпуска исполняется так же, а `gh` в `PATH` подменяет заглушка с готовыми ответами.
Гейт ключа развёртывания исполняется с пустым и непустым значением секрета.
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


# Заглушка `gh`: пишет аргументы в журнал и отвечает содержимым файла по виду запроса —
# так же, как ответил бы `gh api --jq`. Нет файла ответа — `gh` завершается ошибкой, как при 403.
GH_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_DIR/calls"
case "$2" in
    *milestones*) answer="$STUB_DIR/milestones" ;;
    *issues*) answer="$STUB_DIR/issues" ;;
esac
[ -f "$answer" ] || { echo "HTTP 403" >&2; exit 1; }
cat "$answer"
"""


def _gate(
    tmp_path: Path, *, milestones: str | None, issues: str | None = ""
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Исполнить гейт задач выпуска для номера 0.3.0 с заглушкой `gh`."""
    script = _steps()[_step_index("Нет milestone")]["run"]
    stub = tmp_path / "bin" / "gh"
    stub.parent.mkdir()
    stub.write_text(GH_STUB)
    stub.chmod(0o755)
    for name, answer in (("milestones", milestones), ("issues", issues)):
        if answer is not None:
            (tmp_path / name).write_text(answer)
    result = subprocess.run(
        ["sh", "-e", "-c", script],
        cwd=tmp_path,
        env={
            "PATH": f"{stub.parent}:/usr/bin:/bin",
            "STUB_DIR": str(tmp_path),
            "NEXT": "0.3.0",
            "GITHUB_REPOSITORY": "owner/repo",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    calls = tmp_path / "calls"
    return result, calls.read_text().splitlines() if calls.exists() else []


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


def test_write_permission_only_for_release_job() -> None:
    jobs = _workflow()["jobs"]

    assert _workflow()["permissions"] == {"contents": "read"}
    assert jobs["release"]["permissions"] == {"contents": "write", "issues": "read"}
    assert jobs["checks"]["permissions"] == {"contents": "read"}


def test_release_runs_after_checks() -> None:
    jobs = _workflow()["jobs"]

    assert list(jobs) == ["checks", "release"]
    assert jobs["checks"]["uses"] == "./.github/workflows/checks.yml"
    assert jobs["release"]["needs"] == "checks"


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


def _uses_index(action: str) -> int:
    """Номер первого шага, вызывающего действие `action`."""
    return next(
        index
        for index, step in enumerate(_steps())
        if step.get("uses", "").split("@", 1)[0] == action
    )


def test_deploy_key_gate_between_branch_gate_and_checkout() -> None:
    gate = _step_index("RELEASE_DEPLOY_KEY")
    step = _steps()[gate]

    assert 0 < gate < _uses_index("actions/checkout")
    assert "${{" not in step["run"]
    assert step["env"]["RELEASE_DEPLOY_KEY"] == "${{ secrets.RELEASE_DEPLOY_KEY }}"


def test_checkout_uses_deploy_key() -> None:
    step = _steps()[_uses_index("actions/checkout")]

    assert step["with"]["ssh-key"] == "${{ secrets.RELEASE_DEPLOY_KEY }}"
    assert "persist-credentials" not in step["with"]


def test_git_push_is_never_forced() -> None:
    pushes = [
        line for step in _steps() for line in step.get("run", "").splitlines() if "git push" in line
    ]

    assert pushes
    assert not any("--force" in line or " -f" in line for line in pushes)


def _deploy_key_gate(key: str) -> subprocess.CompletedProcess[str]:
    script = _steps()[_step_index("RELEASE_DEPLOY_KEY")]["run"]
    return subprocess.run(
        ["sh", "-e", "-c", script],
        env={"PATH": "/usr/bin:/bin", "RELEASE_DEPLOY_KEY": key},
        capture_output=True,
        text=True,
        check=False,
    )


def test_deploy_key_gate_stops_without_key() -> None:
    result = _deploy_key_gate("")

    assert result.returncode != 0
    assert "RELEASE_DEPLOY_KEY не задан" in result.stderr


def test_deploy_key_gate_passes_with_key() -> None:
    result = _deploy_key_gate("-----BEGIN OPENSSH PRIVATE KEY-----")

    assert result.returncode == 0, result.stderr


def test_issues_gate_between_version_and_write() -> None:
    gate = _step_index("Нет milestone")
    step = _steps()[gate]

    assert _steps()[gate - 1].get("id") == "version"
    assert gate < _step_index("git status --porcelain -- VERSION") < _step_index("git commit")
    assert "${{" not in step["run"]
    assert step["env"]["NEXT"] == "${{ steps.version.outputs.next }}"
    assert step["env"]["GH_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"


# --- Гейт задач выпуска ----------------------------------------------------------------------


def test_issues_gate_passes_when_all_closed(tmp_path: Path) -> None:
    result, calls = _gate(tmp_path, milestones="1\n", issues="")

    assert result.returncode == 0, result.stderr
    assert '"v0.3.0"' in calls[0]
    assert "repos/owner/repo/issues?milestone=1&state=open" in calls[1]


def test_issues_gate_stops_on_open_issue(tmp_path: Path) -> None:
    result, _ = _gate(tmp_path, milestones="1\n", issues="#7 LBFR-019: интеграционные тесты в CI\n")

    assert result.returncode != 0
    assert "v0.3.0" in result.stderr
    assert "#7 LBFR-019: интеграционные тесты в CI" in result.stderr


def test_issues_gate_stops_on_open_pull_request(tmp_path: Path) -> None:
    result, _ = _gate(tmp_path, milestones="1\n", issues="#14 LBFR-024: подготовить выпуск 0.3.0\n")

    assert result.returncode != 0
    assert "#14" in result.stderr


def test_issues_gate_stops_without_milestone(tmp_path: Path) -> None:
    result, calls = _gate(tmp_path, milestones="")

    assert result.returncode != 0
    assert "Нет milestone v0.3.0" in result.stderr
    assert len(calls) == 1


def test_issues_gate_stops_when_api_fails(tmp_path: Path) -> None:
    result, _ = _gate(tmp_path, milestones=None)

    assert result.returncode != 0
    assert "HTTP 403" in result.stderr


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
