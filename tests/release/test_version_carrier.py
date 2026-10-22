"""Носитель номера версии: номер записан только в `VERSION`, сборка берёт его оттуда."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")


def _pyproject() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_version_is_single_line_major_minor_patch() -> None:
    text = (ROOT / "VERSION").read_text(encoding="utf-8")

    assert text.endswith("\n")
    assert len(text.splitlines()) == 1
    assert VERSION_PATTERN.fullmatch(text.strip())


def test_pyproject_reads_version_from_version_file() -> None:
    pyproject = _pyproject()
    project = pyproject["project"]
    tool = pyproject["tool"]

    assert isinstance(project, dict) and isinstance(tool, dict)
    assert "version" not in project
    assert project["dynamic"] == ["version"]
    assert tool["hatch"]["version"]["path"] == "VERSION"
    assert {"file": "VERSION"} in tool["uv"]["cache-keys"]


def test_lock_file_has_no_project_version() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))

    packages = [package for package in lock["package"] if package["name"] == "liquibase-forge"]

    assert len(packages) == 1
    assert "version" not in packages[0]
