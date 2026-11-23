"""Плагин forge: манифесты, каталог маркетплейса, состав поставки, навык с шаблонами операций."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = PROJECT_ROOT / "plugins" / "forge-plugin"
MANIFESTS = (PLUGIN / ".zcode-plugin" / "plugin.json", PLUGIN / ".claude-plugin" / "plugin.json")
MARKETPLACE = PROJECT_ROOT / ".claude-plugin" / "marketplace.json"
SKILL = PLUGIN / "skills" / "forge" / "SKILL.md"
# Что репозиторий forge в поставку не отдаёт
NOT_DELIVERED = {"tests", "docs", "openspec", "src", "backlog", ".forge", ".venv"}


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _version(text: str) -> tuple[int, ...]:
    assert re.fullmatch(r"\d+\.\d+\.\d+", text), text
    return tuple(int(part) for part in text.split("."))


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_manifest_is_valid_json_with_skill_directory(manifest: Path) -> None:
    document = _load(manifest)

    assert document["name"] == "forge-plugin"
    assert document["skills"] == "./skills"
    assert document["description"]
    assert (PLUGIN / "skills").is_dir()


def test_manifests_are_identical() -> None:
    assert MANIFESTS[0].read_bytes() == MANIFESTS[1].read_bytes()


def test_manifest_version_is_not_behind_released_version() -> None:
    """На теге vX.Y.Z поле version равно X.Y.Z: манифест не отстаёт от выпущенного номера."""
    released = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()

    assert _version(str(_load(MANIFESTS[0])["version"])) >= _version(released)


def test_marketplace_lists_plugin_and_dependency() -> None:
    entries = {entry["name"]: entry for entry in _load(MARKETPLACE)["plugins"]}

    assert set(entries) == {"forge-plugin", "backlog"}
    assert entries["forge-plugin"]["source"] == "./plugins/forge-plugin"
    assert PLUGIN.is_dir()


def test_marketplace_version_follows_manifest() -> None:
    entries = {entry["name"]: entry for entry in _load(MARKETPLACE)["plugins"]}

    assert entries["forge-plugin"]["version"] == _load(MANIFESTS[0])["version"]


def test_dependency_points_to_formular_backlog() -> None:
    [backlog] = [e for e in _load(MARKETPLACE)["plugins"] if e["name"] == "backlog"]

    assert backlog["source"] == {
        "source": "git-subdir",
        "url": "https://github.com/united-software-platform/formular.git",
        "path": "plugin/backlog",
        "ref": "main",
    }


def test_plugin_carries_only_the_skill() -> None:
    delivered = {path.relative_to(PLUGIN).parts[0] for path in PLUGIN.rglob("*")}

    assert delivered == {"skills", ".zcode-plugin", ".claude-plugin", "README.md"}
    assert not delivered & NOT_DELIVERED


def test_skill_is_in_agent_skills_format() -> None:
    text = (PLUGIN / "skills" / "forge" / "SKILL.md").read_text(encoding="utf-8")

    assert text.startswith("---\n")
    assert re.search(r"^name: forge$", text, re.MULTILINE)
    assert re.search(r"^description: \S", text, re.MULTILINE)


@pytest.mark.parametrize(
    ("template", "version"),
    [
        ("forge-model.md", "1.3.0"),
        ("forge-apply.md", "1.3.0"),
        ("forge-seed.md", "1.1.0"),
        ("forge-seed-apply.md", "1.0.0"),
    ],
)
def test_operation_templates_are_shipped_with_skill(template: str, version: str) -> None:
    """Шаблон начинается комментарием версии, за ним — фронтматтер с его подстановкой."""
    lines = (
        (PLUGIN / "skills" / "forge" / "templates" / template)
        .read_text(encoding="utf-8")
        .splitlines()
    )

    assert lines[0] == f"<!-- template_version: {version} -->"
    assert lines[1:3] == ["---", 'template_version: "{{template_version}}"']


def _skill_body() -> str:
    """Текст навыка без истории версий и с временными пробелами: история остаётся как записана."""
    body = SKILL.read_text(encoding="utf-8").split("\n## Версионирование\n", 1)[0]
    return " ".join(body.split())


def test_skill_runs_cli_by_single_command() -> None:
    body = _skill_body()

    assert "выполняется как `forge …`" in body
    assert "command -v forge" in body
    assert "forge.sh" not in body
    assert "tools/forge-env" not in body


def test_skill_passes_plugin_templates_to_backlog() -> None:
    body = _skill_body()

    assert '--templates "<каталог навыка>/templates"' in body
    assert '--value "templates=<каталог навыка>/templates"' in body
    assert "в проект они не копируются" in body


@pytest.mark.parametrize(("template", "count"), [("forge-model.md", 3), ("forge-seed.md", 3)])
def test_operation_templates_pass_templates_dir_to_nested_generation(
    template: str, count: int
) -> None:
    """Шаблон операции несёт каталог шаблонов во фронтматтере и в командах попыток."""
    text = (PLUGIN / "skills" / "forge" / "templates" / template).read_text(encoding="utf-8")

    assert 'templates: "{{templates}}"' in text
    assert text.count('`--templates "{{templates}}"`') == count


def test_skill_finds_backlog_delivery_directory_in_harness_caches() -> None:
    body = _skill_body()

    assert "BACKLOG_HOME" in body
    assert "~/.zcode/cli/plugins/cache/formular/backlog/<версия>" in body
    assert "~/.claude/plugins/cache/formular/backlog/<версия>" in body


def test_skill_links_stay_inside_plugin() -> None:
    """Ссылки навыка — только его собственные якоря: документы репозитория в плагин не входят."""
    targets = re.findall(r"\]\(([^)]+)\)", _skill_body())

    assert targets
    assert all(target.startswith("#") for target in targets)
