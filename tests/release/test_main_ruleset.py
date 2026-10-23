"""Правила защиты `main`: файл `.github/rulesets/main.json` и скрипт его применения.

Файл — тело запроса к REST API rulesets, поэтому тест читает его так же, как GitHub. Скрипт
`tools/github/apply-ruleset.sh` исполняется через `sh`, а `gh` в `PATH` подменяет заглушка
с готовыми ответами — как в тесте гейта задач релизного сценария.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
RULESET = ROOT / ".github" / "rulesets" / "main.json"
CHECKS_WORKFLOW = ROOT / ".github" / "workflows" / "checks.yml"
APPLY = ROOT / "tools" / "github" / "apply-ruleset.sh"

# Приложение GitHub Actions: обязательная проверка принимается только от него
GITHUB_ACTIONS_APP_ID = 15368


def _ruleset() -> dict[str, Any]:
    loaded = json.loads(RULESET.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _rule(rule_type: str) -> dict[str, Any]:
    return next(rule for rule in _ruleset()["rules"] if rule["type"] == rule_type)


# --- Файл ruleset'а --------------------------------------------------------------------------


def test_ruleset_follows_default_branch() -> None:
    ruleset = _ruleset()

    assert ruleset["target"] == "branch"
    assert ruleset["enforcement"] == "active"
    assert ruleset["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]


def test_name_is_first_key() -> None:
    # Скрипт применения читает имя строкой: ключ name обязан стоять первым
    assert next(iter(_ruleset())) == "name"


def test_required_check_matches_checks_job_name() -> None:
    checks = yaml.safe_load(CHECKS_WORKFLOW.read_text(encoding="utf-8"))
    parameters = _rule("required_status_checks")["parameters"]

    assert parameters["required_status_checks"] == [
        {"context": checks["jobs"]["checks"]["name"], "integration_id": GITHUB_ACTIONS_APP_ID}
    ]
    assert parameters["strict_required_status_checks_policy"] is False


def test_only_deploy_key_bypasses() -> None:
    assert _ruleset()["bypass_actors"] == [
        {"actor_id": None, "actor_type": "DeployKey", "bypass_mode": "always"}
    ]


def test_pull_request_without_approvals() -> None:
    assert _rule("pull_request")["parameters"]["required_approving_review_count"] == 0


def test_force_push_and_deletion_are_forbidden() -> None:
    types = [rule["type"] for rule in _ruleset()["rules"]]

    assert "non_fast_forward" in types
    assert "deletion" in types


# --- Скрипт применения -----------------------------------------------------------------------

# Заглушка `gh`: пишет аргументы в журнал. `repo view` отвечает именем репозитория, список
# ruleset'ов — содержимым файла `existing` (уже отфильтрованным, как при `--jq`). Файл `fail`
# роняет любой вызов `api`, как при 403.
GH_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_DIR/calls"
[ "$1" = repo ] && { echo owner/repo; exit 0; }
[ -f "$STUB_DIR/fail" ] && { echo "HTTP 403" >&2; exit 1; }
case "$*" in
    "api repos/owner/repo/rulesets "*) cat "$STUB_DIR/existing" 2>/dev/null ;;
esac
exit 0
"""


def _apply(
    tmp_path: Path, *args: str, existing: str = "", fail: bool = False
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    stub = tmp_path / "bin" / "gh"
    stub.parent.mkdir()
    stub.write_text(GH_STUB)
    stub.chmod(0o755)
    (tmp_path / "existing").write_text(existing)
    if fail:
        (tmp_path / "fail").write_text("")
    result = subprocess.run(
        ["sh", str(APPLY), *args],
        cwd=tmp_path,
        env={"PATH": f"{stub.parent}:/usr/bin:/bin", "STUB_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    calls = tmp_path / "calls"
    return result, calls.read_text().splitlines() if calls.exists() else []


def test_apply_creates_missing_ruleset(tmp_path: Path) -> None:
    result, calls = _apply(tmp_path, str(RULESET))

    assert result.returncode == 0, result.stderr
    assert '.name == "main"' in calls[1]
    assert calls[2] == f"api -X POST repos/owner/repo/rulesets --input {RULESET}"


def test_apply_updates_existing_ruleset_by_id(tmp_path: Path) -> None:
    result, calls = _apply(tmp_path, str(RULESET), existing="4242\n")

    assert result.returncode == 0, result.stderr
    assert calls[2] == f"api -X PUT repos/owner/repo/rulesets/4242 --input {RULESET}"
    assert not any("POST" in call for call in calls)


def test_apply_reports_api_error(tmp_path: Path) -> None:
    result, _ = _apply(tmp_path, str(RULESET), fail=True)

    assert result.returncode == 1
    assert "HTTP 403" in result.stderr


def test_apply_without_argument_is_usage_error(tmp_path: Path) -> None:
    result, calls = _apply(tmp_path)

    assert result.returncode == 2
    assert "Использование" in result.stderr
    assert calls == []
