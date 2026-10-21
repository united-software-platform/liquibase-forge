"""Принятие в `db/`: копии файлов попытки и `include` в `master.yaml` без повторов."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from forge.operation.application.accepted_state import AcceptanceError
from forge.operation.infrastructure.accepted_state import FileAcceptedState


def _attempt(directory: Path, stamp: str) -> str:
    directory.mkdir(parents=True)
    (directory / "model.yaml").write_text(f"# модель {stamp}\n", encoding="utf-8")
    (directory / "changelog.yaml").write_text(f"# changelog {stamp}\n", encoding="utf-8")
    return str(directory)


def _includes(master: str) -> list[dict[str, object]]:
    document = yaml.safe_load(Path(master).read_text(encoding="utf-8"))
    return [entry["include"] for entry in document["databaseChangeLog"]]


def test_first_acceptance(tmp_path: Path) -> None:
    state = FileAcceptedState(tmp_path / "db")

    files = state.accept("20261017-153000", _attempt(tmp_path / "attempt-2", "a"))

    assert Path(files.model).read_text(encoding="utf-8") == "# модель a\n"
    assert files.changelog == f"{(tmp_path / 'db').as_posix()}/changelog/20261017-153000.yaml"
    assert Path(files.changelog).read_text(encoding="utf-8") == "# changelog a\n"
    assert _includes(files.master) == [
        {"file": "20261017-153000.yaml", "relativeToChangelogFile": True}
    ]


def test_repeated_acceptance_changes_nothing(tmp_path: Path) -> None:
    state = FileAcceptedState(tmp_path / "db")
    attempt = _attempt(tmp_path / "attempt-1", "a")
    files = state.accept("20261017-153000", attempt)
    before = Path(files.master).read_bytes()

    state.accept("20261017-153000", attempt)

    assert Path(files.master).read_bytes() == before


def test_two_operations_in_order_of_acceptance(tmp_path: Path) -> None:
    state = FileAcceptedState(tmp_path / "db")
    state.accept("20261017-153000", _attempt(tmp_path / "op1", "a"))

    files = state.accept("20261018-090000", _attempt(tmp_path / "op2", "b"))

    assert [i["file"] for i in _includes(files.master)] == [
        "20261017-153000.yaml",
        "20261018-090000.yaml",
    ]
    assert Path(files.model).read_text(encoding="utf-8") == "# модель b\n"


def test_attempt_without_changelog(tmp_path: Path) -> None:
    directory = tmp_path / "attempt-1"
    directory.mkdir()
    (directory / "model.yaml").write_text("x", encoding="utf-8")

    with pytest.raises(AcceptanceError, match=r"changelog\.yaml"):
        FileAcceptedState(tmp_path / "db").accept("20261017-153000", str(directory))

    assert not (tmp_path / "db").exists()


def test_foreign_master_is_refused(tmp_path: Path) -> None:
    master = tmp_path / "db" / "changelog" / "master.yaml"
    master.parent.mkdir(parents=True)
    master.write_text("- просто список\n", encoding="utf-8")

    with pytest.raises(AcceptanceError):
        FileAcceptedState(tmp_path / "db").accept(
            "20261017-153000", _attempt(tmp_path / "attempt-1", "a")
        )
