"""Обёртка `tools/forge-env/forge.sh`: выбор команды uv, передача аргументов и кода возврата.

`uv` подменяется заглушкой в `PATH`: она печатает свои аргументы и выходит с заданным кодом.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.delivery.support import ROOT

WRAPPER = ROOT / "tools" / "forge-env" / "forge.sh"


@pytest.fixture
def fake_uv(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit "${FAKE_UV_EXIT:-0}"\n')
    uv.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}


def _run(project: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(WRAPPER), *args],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_target_project_runs_forge_subproject(tmp_path: Path, fake_uv: dict[str, str]) -> None:
    project = tmp_path / "project"
    (project / "tools" / "forge").mkdir(parents=True)
    (project / "tools" / "forge" / "pyproject.toml").write_text("[project]\n")

    result = _run(project, fake_uv, "status", "--latest")

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "run",
        "--project",
        "tools/forge",
        "--frozen",
        "--no-dev",
        "forge",
        "status",
        "--latest",
    ]


def test_forge_repository_runs_root_project(tmp_path: Path, fake_uv: dict[str, str]) -> None:
    project = tmp_path / "project"
    project.mkdir()

    result = _run(project, fake_uv, "report", "--operation", "path with space")

    assert result.returncode == 0
    expected = ["run", "forge", "report", "--operation", "path with space"]
    assert result.stdout.splitlines() == expected


@pytest.mark.parametrize("code", [1, 2])
def test_exit_code_is_passed_through(tmp_path: Path, fake_uv: dict[str, str], code: int) -> None:
    project = tmp_path / "project"
    (project / "tools" / "forge").mkdir(parents=True)
    (project / "tools" / "forge" / "pyproject.toml").write_text("[project]\n")

    result = _run(project, {**fake_uv, "FAKE_UV_EXIT": str(code)}, "validate")

    assert result.returncode == code
