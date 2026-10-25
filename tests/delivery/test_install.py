"""Установщик `install.sh`: сценарии спецификации `forge-delivery` на локальном источнике.

Установщик запускается `sh install.sh --source <корень репозитория>` во временном проекте
с поддельным `.sdd-kit-manifest.json` и файлами kit'а без блоков forge. Сеть не нужна:
путь `--ref` и `releases/latest` проверяется ручным прогоном при релизе.
"""

from __future__ import annotations

import hashlib
import os
import pty
import re
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.delivery.support import (
    BEGIN_MARKER,
    BLOCKS_DIR,
    END_MARKER,
    ROOT,
    delivery_entries,
    marked_block,
)

INSTALLER = ROOT / "install.sh"
KIT_FILES = ("Makefile", ".env.example", "docker-compose.yml", "tools/host-runner/runner.py")
BLOCK_PATTERN = re.compile(r"[ \t]*# >>> liquibase-forge\n.*?# <<< liquibase-forge\n", re.S)
RUNNER_FIXTURES = ROOT / "tests" / "delivery" / "fixtures" / "runner"
RUNNER = "tools/host-runner/runner.py"
KIT_TARGETS = frozenset({"init", "openspec-init", "help"})
FORGE_TARGETS = frozenset(
    {"liquibase-update", "liquibase-rollback", "forge-env-sync", "forge-env-check", "forge-env-up"}
)


def _kit_text(path: str) -> str:
    """Файл kit'а в том виде, в каком его ставит установщик kit'а: без блока forge."""
    text = BLOCK_PATTERN.sub("", (ROOT / path).read_text(encoding="utf-8"))
    return text.replace("include:\n\n", "") if path == "docker-compose.yml" else text


def _write_kit_manifest(project: Path, version: str) -> None:
    (project / ".sdd-kit-manifest.json").write_text(
        f'{{\n  "kit_version": "{version}",\n  "kit_ref": "v{version}",\n  "files": []\n}}\n'
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    for path in KIT_FILES:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(_kit_text(path))
    (root / ".gitignore").write_text(".env\n.ssh/\n")
    (root / "pyproject.toml").write_text('[project]\nname = "shop"\nversion = "3.1.0"\n')
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('shop')\n")
    (root / "README.md").write_text("# shop\n")
    _write_kit_manifest(root, "1.5.0")
    return root


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _install(project: Path, *args: str, source: Path = ROOT) -> subprocess.CompletedProcess[str]:
    # stdin закрыт, а сеанс отделён от терминала: /dev/tty недоступен, как в CI
    return subprocess.run(
        ["sh", str(INSTALLER), "--source", str(source), *args],
        cwd=project,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        start_new_session=True,
    )


def _install_with_answer(project: Path, answer: str) -> tuple[int, str]:
    """Запуск в псевдотерминале: вопрос установщика получает ответ через /dev/tty."""
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(project)
        os.execvp("sh", ["sh", str(INSTALLER), "--source", str(ROOT)])
    os.write(fd, f"{answer}\n".encode())
    output = b""
    while True:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), output.decode(errors="replace")


# --- Предусловие и ключи ---------------------------------------------------------------------


def test_project_without_kit_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    result = _install(empty)

    assert result.returncode == 1
    assert list(empty.iterdir()) == []


def test_old_kit_is_refused(project: Path) -> None:
    _write_kit_manifest(project, "1.4.2")
    before = _snapshot(project)

    result = _install(project)

    assert result.returncode == 1
    assert "1.4.2" in result.stderr and "1.5.0" in result.stderr
    assert _snapshot(project) == before


def test_ref_and_source_are_mutually_exclusive(project: Path) -> None:
    before = _snapshot(project)

    result = _install(project, "--ref", "v0.2.0")

    assert result.returncode == 2
    assert _snapshot(project) == before


def test_unknown_key_is_refused(project: Path) -> None:
    before = _snapshot(project)

    result = _install(project, "--force")

    assert result.returncode == 2
    assert _snapshot(project) == before


def test_version_without_installer_is_refused(project: Path, tmp_path: Path) -> None:
    old_version = tmp_path / "forge-v0.1.0"
    old_version.mkdir()
    (old_version / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    before = _snapshot(project)

    result = _install(project, source=old_version)

    assert result.returncode == 1
    assert "delivery.txt" in result.stderr
    assert _snapshot(project) == before


def _source_copy(destination: Path) -> Path:
    """Копия поставки forge: перечень, фрагменты блоков и источники `delivery.txt`."""
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    destination.mkdir()
    shutil.copy2(ROOT / "delivery.txt", destination / "delivery.txt")
    shutil.copytree(ROOT / "install", destination / "install", ignore=ignore)
    for source, _ in delivery_entries():
        (destination / source).parent.mkdir(parents=True, exist_ok=True)
        if (ROOT / source).is_dir():
            shutil.copytree(ROOT / source, destination / source, ignore=ignore)
        else:
            shutil.copy2(ROOT / source, destination / source)
    return destination


# None — файла VERSION в источнике нет
@pytest.mark.parametrize("version", ["0.2\n", "v0.2.0\n", "", None])
def test_unreadable_version_is_refused(project: Path, tmp_path: Path, version: str | None) -> None:
    source = _source_copy(tmp_path / "forge")
    if version is None:
        (source / "VERSION").unlink()
    else:
        (source / "VERSION").write_text(version)
    before = _snapshot(project)

    result = _install(project, source=source)

    assert result.returncode == 1
    assert "VERSION" in result.stderr
    assert _snapshot(project) == before


# --- План ------------------------------------------------------------------------------------


def test_unrecognized_insertion_place_is_refused(project: Path) -> None:
    runner = project / "tools" / "host-runner" / "runner.py"
    runner.write_text('TARGETS = {"init", "help"}\n')
    before = _snapshot(project)

    result = _install(project)

    assert result.returncode == 1
    assert "tools/host-runner/runner.py" in result.stderr
    assert "сразу после присваивания ALLOWED_TARGETS" in result.stderr
    assert (BLOCKS_DIR / "runner.py").read_text() in result.stdout
    assert _snapshot(project) == before


def test_dry_run_prints_plan_and_writes_nothing(project: Path) -> None:
    before = _snapshot(project)

    result = _install(project, "--dry-run")

    assert result.returncode == 0
    assert "создать: файл tools/forge/pyproject.toml" in result.stdout
    assert "создать: блок forge в tools/host-runner/runner.py" in result.stdout
    assert _snapshot(project) == before


# --- Подтверждение правок владельца ----------------------------------------------------------


def _owner_edit(project: Path) -> Path:
    assert _install(project).returncode == 0
    gateway = project / "tools" / "liquibase" / "gateway.py"
    gateway.write_text(gateway.read_text() + "# правка владельца\n")
    return gateway


def test_refusal_to_overwrite_owner_edit(project: Path) -> None:
    _owner_edit(project)
    before = _snapshot(project)

    code, output = _install_with_answer(project, "n")

    assert code == 1
    assert "правка владельца, перезаписать: файл tools/liquibase/gateway.py" in output
    assert _snapshot(project) == before


def test_owner_edit_without_terminal_is_refused(project: Path) -> None:
    _owner_edit(project)
    before = _snapshot(project)

    result = _install(project)

    assert result.returncode == 1
    assert "--yes" in result.stderr
    assert _snapshot(project) == before


def test_owner_edit_is_overwritten_after_confirmation(project: Path) -> None:
    gateway = _owner_edit(project)

    code, _ = _install_with_answer(project, "y")

    assert code == 0
    assert gateway.read_bytes() == (ROOT / "tools" / "liquibase" / "gateway.py").read_bytes()


def test_owner_edit_is_overwritten_with_yes(project: Path) -> None:
    gateway = _owner_edit(project)

    result = _install(project, "--yes")

    assert result.returncode == 0
    assert gateway.read_bytes() == (ROOT / "tools" / "liquibase" / "gateway.py").read_bytes()


def test_owner_edit_inside_block_needs_confirmation(project: Path) -> None:
    assert _install(project).returncode == 0
    makefile = project / "Makefile"
    makefile.write_text(makefile.read_text().replace("forge-env-up: ##", "forge-env-up: ## !"))
    before = _snapshot(project)

    result = _install(project)

    assert result.returncode == 1
    assert "правка владельца, перезаписать: блок forge в Makefile" in result.stdout
    assert _snapshot(project) == before


# --- Запись ----------------------------------------------------------------------------------


def test_manifest_lists_files_and_five_blocks(project: Path) -> None:
    assert _install(project).returncode == 0

    manifest = (project / ".forge-manifest.json").read_text()

    assert '"forge_ref": "local"' in manifest
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert f'"forge_version": "{version}"' in manifest
    assert re.search(r'"installed_at": "\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"', manifest)
    blocks = manifest.split('"blocks"')[1]
    assert blocks.count('"sha256"') == 5
    assert '"path": "tools/forge/src/forge/cli/main.py"' in manifest
    assert '"path": "tools/forge/uv.lock"' in manifest
    assert '"path": "tools/forge/VERSION"' in manifest


def test_cli_code_does_not_touch_project(project: Path) -> None:
    pyproject = (project / "pyproject.toml").read_bytes()

    assert _install(project).returncode == 0

    assert (project / "pyproject.toml").read_bytes() == pyproject
    assert sorted(path.name for path in (project / "src").iterdir()) == ["app.py"]
    assert (project / "tools" / "forge" / "src" / "forge" / "cli" / "main.py").is_file()
    assert (project / "tools" / "forge" / "pyproject.toml").read_bytes() == (
        ROOT / "pyproject.toml"
    ).read_bytes()


def test_tests_and_documents_are_not_delivered(project: Path) -> None:
    assert _install(project).returncode == 0

    for path in ("tests", "openspec", "docs", "install", "delivery.txt", "install.sh"):
        assert not (project / path).exists(), path
    assert (project / "README.md").read_text() == "# shop\n"
    assert not list(project.rglob("__pycache__"))


def test_blocks_are_written_between_markers(project: Path) -> None:
    assert _install(project).returncode == 0

    for fragment, path in (
        ("Makefile", "Makefile"),
        ("env.example", ".env.example"),
        ("docker-compose.yml", "docker-compose.yml"),
        ("runner.py", "tools/host-runner/runner.py"),
        ("gitignore", ".gitignore"),
    ):
        text = (project / path).read_text()
        assert marked_block(text) == (BLOCKS_DIR / fragment).read_text(), path
        assert BLOCK_PATTERN.sub("", text).replace("include:\n\n", "") == (
            ".env\n.ssh/\n\n" if path == ".gitignore" else _kit_text(path)
        ), path


def test_installed_files_match_forge_repository(project: Path) -> None:
    assert _install(project).returncode == 0

    for path in ("Makefile", ".env.example", "docker-compose.yml", "tools/host-runner/runner.py"):
        assert (project / path).read_bytes() == (ROOT / path).read_bytes(), path


def test_operation_templates_are_installed(project: Path) -> None:
    assert _install(project).returncode == 0

    for name in ("forge-model.md", "forge-apply.md", "forge-seed.md", "forge-seed-apply.md"):
        path = f"templates/{name}"
        assert (project / path).read_bytes() == (ROOT / path).read_bytes(), path


def test_owner_change_outside_markers_survives_reinstall(project: Path) -> None:
    assert _install(project).returncode == 0
    makefile = project / "Makefile"
    makefile.write_text(makefile.read_text() + "\nshop-seed: ## Наполнить БД магазина\n\t@true\n")
    fragment = BLOCKS_DIR / "Makefile"
    block = marked_block(makefile.read_text())
    makefile.write_text(makefile.read_text().replace(block, "# устаревший блок forge\n"))
    manifest = project / ".forge-manifest.json"
    manifest.write_text(
        re.sub(
            r'("path": "Makefile", "sha256": ")[0-9a-f]+',
            lambda match: match.group(1) + _sha256("# устаревший блок forge\n"),
            manifest.read_text(),
        )
    )

    result = _install(project)

    assert result.returncode == 0, result.stderr
    assert "обновить: блок forge в Makefile" in result.stdout
    text = makefile.read_text()
    assert "shop-seed: ## Наполнить БД магазина\n\t@true\n" in text
    assert marked_block(text) == fragment.read_text()


def test_block_lost_after_kit_reinstall_is_inserted_again(project: Path) -> None:
    assert _install(project).returncode == 0
    runner = project / "tools" / "host-runner" / "runner.py"
    runner.write_text(_kit_text("tools/host-runner/runner.py"))

    result = _install(project)

    assert result.returncode == 0, result.stderr
    assert "создать: блок forge в tools/host-runner/runner.py" in result.stdout
    assert marked_block(runner.read_text()) == (BLOCKS_DIR / "runner.py").read_text()


def test_compose_with_own_include_gets_list_item(project: Path) -> None:
    compose = project / "docker-compose.yml"
    compose.write_text("include:\n  - path: shop/compose.yaml\n\n" + compose.read_text())

    assert _install(project).returncode == 0

    text = compose.read_text()
    assert text.count("include:") == 1
    assert text.startswith(f"include:\n  {BEGIN_MARKER}\n")
    assert f"  {END_MARKER}\n  - path: shop/compose.yaml\n" in text


def test_repeated_install_changes_nothing(project: Path) -> None:
    assert _install(project).returncode == 0
    after_first = _snapshot(project)

    result = _install(project)

    assert result.returncode == 0
    assert "Менять нечего" in result.stdout
    assert _snapshot(project) == after_first


def test_end_of_install_names_next_steps(project: Path) -> None:
    result = _install(project)

    assert result.returncode == 0
    assert "Перезапустите раннер" in result.stdout
    assert "make forge-env-sync" in result.stdout
    assert "make forge-env-check" in result.stdout


def test_unmarked_forge_differences_are_reported(project: Path) -> None:
    runner = project / "tools" / "host-runner" / "runner.py"
    # Отличия forge, внесённые владельцем вручную: текст фрагмента без маркеров
    runner.write_text(runner.read_text() + (BLOCKS_DIR / "runner.py").read_text())

    result = _install(project, "--dry-run")

    assert result.returncode == 0
    assert "вне маркеров" in result.stdout
    assert "  tools/host-runner/runner.py" in result.stdout


# --- Блок раннера: формы белого списка и перенос блока 0.3.0 ---------------------------------


def _runner_globals(path: Path) -> dict[str, object]:
    """Пространство имён раннера без запуска сервера: main() вызывается только из __main__."""
    return runpy.run_path(str(path), run_name="forge_runner_under_test")


def _without_block(text: str) -> str:
    """Текст файла без маркеров forge и строк между ними."""
    return BLOCK_PATTERN.sub("", text)


def _write_forge_manifest(project: Path, block_sum: str) -> None:
    """Манифест прежней установки, в котором известна только сумма блока раннера."""
    (project / ".forge-manifest.json").write_text(
        "{\n"
        '  "files": [],\n'
        '  "blocks": [\n'
        f'    {{"path": "{RUNNER}", "sha256": "{block_sum}"}}\n'
        "  ]\n"
        "}\n"
    )


@pytest.mark.parametrize("form", ["kit-1.5.0.py", "multiline.py", "dictionary.py"])
def test_runner_whitelist_form_gets_forge_targets(project: Path, form: str) -> None:
    original = (RUNNER_FIXTURES / form).read_text()
    runner = project / RUNNER
    runner.write_text(original)

    result = _install(project)

    assert result.returncode == 0, result.stderr
    text = runner.read_text()
    compile(text, str(runner), "exec")
    names = _runner_globals(runner)
    allowed = names["ALLOWED_TARGETS"]
    assert isinstance(allowed, frozenset)
    assert allowed >= KIT_TARGETS | FORGE_TARGETS
    if "TARGET_VARIABLES" in names:
        before = _runner_globals(RUNNER_FIXTURES / form)["TARGET_VARIABLES"]
        after = names["TARGET_VARIABLES"]
        assert isinstance(before, dict) and isinstance(after, dict)
        assert {target: after[target] for target in FORGE_TARGETS} == dict.fromkeys(
            FORGE_TARGETS, frozenset()
        )
        assert {target: after[target] for target in before} == before
    assert _without_block(text) == original


def test_runner_block_follows_kit_whitelist_line(project: Path) -> None:
    runner = project / RUNNER
    runner.write_text((RUNNER_FIXTURES / "kit-1.5.0.py").read_text())

    assert _install(project).returncode == 0

    lines = runner.read_text().splitlines()
    assignment = next(i for i, line in enumerate(lines) if line.startswith("ALLOWED_TARGETS ="))
    assert lines[assignment + 1] == BEGIN_MARKER


def test_runner_block_of_forge_0_3_0_is_moved_out_of_literal(project: Path) -> None:
    installed = (RUNNER_FIXTURES / "multiline-forge-0.3.0.py").read_text()
    runner = project / RUNNER
    runner.write_text(installed)
    _write_forge_manifest(project, _sha256(marked_block(installed)))

    result = _install(project)

    assert result.returncode == 0, result.stderr
    assert f"обновить: блок forge в {RUNNER}" in result.stdout
    text = runner.read_text()
    compile(text, str(runner), "exec")
    allowed = _runner_globals(runner)["ALLOWED_TARGETS"]
    assert isinstance(allowed, frozenset)
    assert allowed >= KIT_TARGETS | FORGE_TARGETS
    assert f"    {BEGIN_MARKER}" not in text
    assert _without_block(text) == (RUNNER_FIXTURES / "multiline.py").read_text()


def test_owner_edited_runner_block_inside_literal_needs_confirmation(project: Path) -> None:
    runner = project / RUNNER
    runner.write_text((RUNNER_FIXTURES / "multiline-forge-0.3.0.py").read_text())
    _write_forge_manifest(project, _sha256("правка владельца\n"))
    before = _snapshot(project)

    result = _install(project)

    assert result.returncode == 1
    assert f"правка владельца, перезаписать: блок forge в {RUNNER}" in result.stdout
    assert _snapshot(project) == before
