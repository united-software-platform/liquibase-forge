"""Команда `forge generate-seed`: сценарии спецификации `forge-seed-migration` через `main`."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from forge.cli.main import main
from tests.migration.operation_backlog import write_operation
from tests.seeding.support import EXAMPLE_STAMP, MIGRATION_EXAMPLE


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, Any]]:
    code = main(argv)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    payload = json.loads(lines[0])
    assert isinstance(payload, dict)
    return code, payload


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Корень проекта текущим каталогом: модель и принятый seed примера в `db/`, seed попытки
    и беклог операции в `interactive`."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FORGE_ACCEPTED_DIR", raising=False)
    (tmp_path / "db").mkdir()
    shutil.copyfile(MIGRATION_EXAMPLE / "model.yaml", tmp_path / "db" / "model.yaml")
    shutil.copyfile(MIGRATION_EXAMPLE / "accepted.yaml", tmp_path / "db" / "seed.yaml")
    shutil.copyfile(MIGRATION_EXAMPLE / "attempt.yaml", tmp_path / "seed.yaml")
    write_operation(tmp_path, subject=EXAMPLE_STAMP, mode="interactive")
    return tmp_path


def _generate(
    capsys: pytest.CaptureFixture[str], *options: str, out: str = "attempt-1/changelog.yaml"
) -> tuple[int, dict[str, Any]]:
    argv = ["generate-seed", "--seed", "seed.yaml", "--operation", "tasks.md", "--out", out]
    return _run([*argv, *options], capsys)


def test_successful_build(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _generate(capsys)

    assert code == 0
    assert payload["changelog"] == "attempt-1/changelog.yaml"
    assert payload["logical_file_path"] == f"db/changelog/{EXAMPLE_STAMP}.yaml"
    assert payload["changesets"] == [
        {"id": f"{EXAMPLE_STAMP}-01", "kind": "insert_rows", "table": "status_group", "rows": 1},
        {"id": f"{EXAMPLE_STAMP}-02", "kind": "insert_rows", "table": "order_status", "rows": 2},
        {"id": f"{EXAMPLE_STAMP}-03", "kind": "update_rows", "table": "order_status", "rows": 1},
        {"id": f"{EXAMPLE_STAMP}-04", "kind": "delete_rows", "table": "order_status", "rows": 1},
    ]
    assert payload["deleted_rows"] == [{"table": "order_status", "key": {"code": "archived"}}]
    assert (payload["violations"], payload["unsupported"]) == ([], [])
    written = (project / "attempt-1" / "changelog.yaml").read_text(encoding="utf-8")
    assert written == (MIGRATION_EXAMPLE / "changelog.yaml").read_text(encoding="utf-8")


def test_repeated_generation_is_byte_identical(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _generate(capsys, out="first.yaml")
    _generate(capsys, out="second.yaml")

    assert (project / "first.yaml").read_bytes() == (project / "second.yaml").read_bytes()


def test_first_fill_without_accepted_seed(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "db" / "seed.yaml").unlink()

    code, payload = _generate(capsys)

    assert code == 0
    assert {c["kind"] for c in payload["changesets"]} == {"insert_rows"}
    assert payload["deleted_rows"] == []


def test_explicit_sources(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shutil.move(project / "db", project / "elsewhere")

    code, payload = _generate(
        capsys,
        "--accepted-seed", "elsewhere/seed.yaml",
        "--model", "elsewhere/model.yaml",
    )  # fmt: skip

    assert (code, len(payload["changesets"])) == (0, 4)


def test_equal_seeds_give_empty_changelog(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copyfile(project / "db" / "seed.yaml", project / "seed.yaml")

    code, payload = _generate(capsys)

    assert (code, payload["changesets"]) == (0, [])
    text = (project / "attempt-1" / "changelog.yaml").read_text(encoding="utf-8")
    assert yaml.safe_load(text) == {"databaseChangeLog": []}


def test_seed_violation_is_code_1_and_removes_old_changelog(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "attempt-1").mkdir()
    (project / "attempt-1" / "changelog.yaml").write_text("устаревший", encoding="utf-8")
    (project / "seed.yaml").write_text(
        "version: 1\ntables:\n  - name: status_group\n    rows:\n      - {title: Без кода}\n",
        encoding="utf-8",
    )

    code, payload = _generate(capsys)

    assert (code, payload["changelog"]) == (1, None)
    assert [(v["path"], v["code"]) for v in payload["violations"]] == [
        ("tables[0].rows[0].code", "null_value")
    ]
    assert not (project / "attempt-1" / "changelog.yaml").exists()


def test_unique_swap_is_code_1_with_unsupported(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    accepted = (project / "db" / "seed.yaml").read_text(encoding="utf-8")
    (project / "seed.yaml").write_text(
        accepted.replace("title: Черновик", "title: Новый").replace(
            "{code: archived, group_code: active, title: Архив",
            "{code: archived, group_code: active, title: Черновик",
        ),
        encoding="utf-8",
    )

    code, payload = _generate(capsys)

    assert (code, payload["changelog"]) == (1, None)
    (conflict,) = payload["unsupported"]
    assert (conflict["table"], conflict["columns"]) == ("order_status", ["title"])
    assert conflict["rows"] == ["order_status[code=archived]", "order_status[code=draft]"]


def test_deletion_without_consent_in_auto_is_code_2(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_operation(project, subject=EXAMPLE_STAMP, mode="auto", allow_drop=False)

    code, payload = _generate(capsys)

    assert code == 2
    assert payload["error"]["kind"] == "drop_not_allowed"
    assert payload["error"]["objects"] == ["order_status[code=archived]"]
    assert not (project / "attempt-1" / "changelog.yaml").exists()


def test_deletion_with_consent_in_auto(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_operation(project, subject=EXAMPLE_STAMP, mode="auto", allow_drop=True)

    code, payload = _generate(capsys)

    assert (code, len(payload["deleted_rows"])) == (0, 1)


@pytest.mark.parametrize(
    ("prepare", "kind"),
    [
        (lambda p: (p / "tasks.md").unlink(), "operation_unavailable"),
        (lambda p: (p / "seed.yaml").unlink(), "seed_unreadable"),
        (lambda p: _replace_with_directory(p / "db" / "model.yaml"), "model_unreadable"),
        (
            lambda p: (p / "db" / "model.yaml").write_text("version: 2\n", encoding="utf-8"),
            "accepted_model_invalid",
        ),
        (
            lambda p: (p / "db" / "seed.yaml").write_text(
                "version: 1\ntables:\n  - {name: unknown, rows: []}\n", encoding="utf-8"
            ),
            "accepted_seed_invalid",
        ),
    ],
)
def test_environment_errors_are_code_2(
    project: Path, capsys: pytest.CaptureFixture[str], prepare: Any, kind: str
) -> None:
    prepare(project)

    code, payload = _generate(capsys)

    assert (code, payload["error"]["kind"]) == (2, kind)


def _replace_with_directory(path: Path) -> None:
    path.unlink()
    path.mkdir()


def test_invalid_accepted_root(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FORGE_ACCEPTED_DIR", "../outside")

    code, payload = _generate(capsys)

    assert (code, payload["error"]["kind"]) == (2, "accepted_root_invalid")
