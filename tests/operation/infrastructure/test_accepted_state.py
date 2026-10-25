"""Принятие в `db/`: копии файлов попытки и `include` в `master.yaml` без повторов."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from forge.operation.application.accepted_state import AcceptanceError
from forge.operation.infrastructure.accepted_state import FileAcceptedState
from forge.seeding.domain.draft import RawValue, ScalarKind
from forge.seeding.infrastructure.yaml_reader import YamlSeedDraftReader


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


def _seed_attempt(directory: Path, stamp: str) -> str:
    directory.mkdir(parents=True)
    (directory / "seed.yaml").write_text(f"# seed {stamp}\n", encoding="utf-8")
    (directory / "changelog.yaml").write_text(f"# changelog данных {stamp}\n", encoding="utf-8")
    return str(directory)


def test_first_seed_acceptance(tmp_path: Path) -> None:
    state = FileAcceptedState(tmp_path / "db")
    model = state.accept("20261017-153000", _attempt(tmp_path / "model-1", "a"))
    model_before = Path(str(model.model)).read_bytes()

    files = state.accept_seed("20261025-101500", _seed_attempt(tmp_path / "seed-1", "s"))

    db = (tmp_path / "db").as_posix()
    assert (files.model, files.seed) == (None, f"{db}/seed.yaml")
    assert Path(str(files.seed)).read_text(encoding="utf-8") == "# seed s\n"
    assert files.changelog == f"{db}/changelog/20261025-101500.yaml"
    assert Path(files.changelog).read_text(encoding="utf-8") == "# changelog данных s\n"
    assert [i["file"] for i in _includes(files.master)] == [
        "20261017-153000.yaml",
        "20261025-101500.yaml",
    ]
    assert Path(str(model.model)).read_bytes() == model_before


def test_repeated_seed_acceptance_changes_nothing(tmp_path: Path) -> None:
    state = FileAcceptedState(tmp_path / "db")
    attempt = _seed_attempt(tmp_path / "seed-1", "s")
    files = state.accept_seed("20261025-101500", attempt)
    before = Path(files.master).read_bytes()

    again = state.accept_seed("20261025-101500", attempt)

    assert again == files == state.seed_files("20261025-101500")
    assert Path(files.master).read_bytes() == before


def test_seed_attempt_without_seed(tmp_path: Path) -> None:
    directory = tmp_path / "seed-1"
    directory.mkdir()
    (directory / "changelog.yaml").write_text("x", encoding="utf-8")

    with pytest.raises(AcceptanceError, match=r"seed\.yaml"):
        FileAcceptedState(tmp_path / "db").accept_seed("20261025-101500", str(directory))

    assert not (tmp_path / "db").exists()


SEED = """version: 1
tables:
  - name: order_status
    rows:
      - {code: draft, title: Черновик, color: grey, since: 2026-10-01T10:00:00Z}
      - code: paid
        title: "Оплачен"
        fee: "0.00"
        color: red
  - name: status_group
    rows: []
"""

DROP_COLUMN_CHANGELOG = """databaseChangeLog:
- changeSet:
    id: 20261026-090000-01
    changes:
    - dropColumn:
        tableName: order_status
        columnName: color
"""


def _model_attempt(directory: Path, changelog: str) -> str:
    directory.mkdir(parents=True)
    (directory / "model.yaml").write_text("# модель\n", encoding="utf-8")
    (directory / "changelog.yaml").write_text(changelog, encoding="utf-8")
    return str(directory)


def test_dropped_seed_column_leaves_accepted_seed(tmp_path: Path) -> None:
    db = tmp_path / "db"
    db.mkdir()
    (db / "seed.yaml").write_text(SEED, encoding="utf-8")

    files = FileAcceptedState(db).accept(
        "20261026-090000", _model_attempt(tmp_path / "attempt-1", DROP_COLUMN_CHANGELOG)
    )

    assert files.seed == (db / "seed.yaml").as_posix()
    reading = YamlSeedDraftReader().read(str(db / "seed.yaml"))
    assert reading.violations == ()
    [status, group] = reading.draft.tables
    assert [[key for key, _ in row.values] for row in status.rows] == [
        ["code", "title", "since"],
        ["code", "title", "fee"],
    ]
    assert dict(status.rows[0].values)["since"] == RawValue(
        ScalarKind.TIMESTAMP, "2026-10-01T10:00:00Z"
    )
    assert dict(status.rows[1].values)["fee"] == RawValue(ScalarKind.STRING, "0.00")
    assert (group.name, group.rows) == ("status_group", ())


def test_seed_untouched_by_model_without_seed_column_drops(tmp_path: Path) -> None:
    db = tmp_path / "db"
    db.mkdir()
    (db / "seed.yaml").write_text(SEED, encoding="utf-8")
    other = DROP_COLUMN_CHANGELOG.replace("order_status", "customer")

    files = FileAcceptedState(db).accept(
        "20261026-090000", _model_attempt(tmp_path / "attempt-1", other)
    )

    assert files.seed is None
    assert (db / "seed.yaml").read_text(encoding="utf-8") == SEED


def test_model_acceptance_without_accepted_seed(tmp_path: Path) -> None:
    files = FileAcceptedState(tmp_path / "db").accept(
        "20261026-090000", _model_attempt(tmp_path / "attempt-1", DROP_COLUMN_CHANGELOG)
    )

    assert files.seed is None
    assert not (tmp_path / "db" / "seed.yaml").exists()
