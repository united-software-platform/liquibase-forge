"""Команда `forge reconcile-seed`: ответ, коды `0`, `1`, `2` и виды ошибок."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from forge.cli.commands import reconcile_seed
from forge.cli.main import main
from forge.shared.infrastructure.json_result_writer import JsonResultWriter
from tests.migration.fakes import FakeSettings
from tests.reconciliation.fakes import FakeChangesets
from tests.seeding.fakes import ACCEPTED, MODEL, SEED, FakeDatabase, files, use_case

ROWS = """version: 1
tables:
  - name: order_status
    rows:
      - {code: draft, title: Черновик}
      - {code: paid, title: Оплачен}
"""


def _run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    db: FakeDatabase,
    paths: dict[str, str | None] | None = None,
    settings: FakeSettings | None = None,
    changesets: FakeChangesets | None = None,
) -> tuple[int, dict[str, Any], str]:
    given = paths if paths is not None else dict(files(tmp_path))
    args = argparse.Namespace(
        seed=given["seed"],
        changelog=given["changelog"],
        accepted_seed=given["accepted_seed"],
        model=given["model"],
    )
    code = reconcile_seed.run(
        args, use_case(tmp_path, db, JsonResultWriter(), settings, changesets)
    )
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    return code, json.loads(lines[0]), out


def _result(tmp_path: Path) -> Path:
    return tmp_path / "attempt-1" / "reconcile.json"


def test_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload, _ = _run(tmp_path, capsys, FakeDatabase(ROWS))

    assert code == 0
    assert payload == {
        "seed": str(tmp_path / "attempt-1" / "seed.yaml"),
        "changelog": str(tmp_path / "attempt-1" / "changelog.yaml"),
        "database": "lbfr-db-test:5432/t_0001",
        "verdict": "success",
        "discrepancies": [],
    }
    assert json.loads(_result(tmp_path).read_text(encoding="utf-8")) == payload


def test_failure_carries_key(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rows = ROWS.replace("      - {code: paid, title: Оплачен}\n", "")

    code, payload, _ = _run(tmp_path, capsys, FakeDatabase(rows))

    assert (code, payload["verdict"]) == (1, "failure")
    assert payload["discrepancies"] == [
        {
            "kind": "row_missing",
            "table": "order_status",
            "key": {"code": "paid"},
            "column": None,
            "changeset": None,
            "expected": "present",
            "actual": "absent",
            "message": "строки order_status[code=paid] нет в БД",
        }
    ]
    assert json.loads(_result(tmp_path).read_text(encoding="utf-8")) == payload


def test_journal_discrepancy_has_null_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload, _ = _run(tmp_path, capsys, FakeDatabase(ROWS, records=()))

    assert code == 1
    (found,) = payload["discrepancies"]
    assert (found["kind"], found["key"]) == ("changeset_not_executed", None)


def test_output_is_stable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rows = ROWS.replace("Черновик", "Набросок")

    _, _, first = _run(tmp_path, capsys, FakeDatabase(rows))
    _, _, second = _run(tmp_path, capsys, FakeDatabase(rows))

    assert first == second


def test_defaults_come_from_accepted_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FORGE_ACCEPTED_DIR", raising=False)
    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "model.yaml").write_text(MODEL, encoding="utf-8")
    (tmp_path / "db" / "seed.yaml").write_text(ACCEPTED, encoding="utf-8")
    (tmp_path / "seed.yaml").write_text(SEED, encoding="utf-8")
    db = FakeDatabase(ROWS)
    paths: dict[str, str | None] = {
        "seed": "seed.yaml",
        "changelog": "attempt-1/changelog.yaml",
        "accepted_seed": None,
        "model": None,
    }
    (tmp_path / "attempt-1").mkdir()

    code, _, _ = _run(tmp_path, capsys, db, paths)

    assert code == 0
    assert db.requested == ["order_status", "legacy_status"], "принятый seed — db/seed.yaml"


def _error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    kind: str,
    paths: dict[str, str | None] | None = None,
    db: FakeDatabase | None = None,
    settings: FakeSettings | None = None,
    changesets: FakeChangesets | None = None,
) -> dict[str, Any]:
    code, payload, _ = _run(tmp_path, capsys, db or FakeDatabase(ROWS), paths, settings, changesets)

    assert (code, payload["error"]["kind"]) == (2, kind)
    assert not _result(tmp_path).exists()
    error: dict[str, Any] = payload["error"]
    return error


def test_database_unavailable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _error(tmp_path, capsys, "database_unavailable", db=FakeDatabase(ROWS, available=False))


def test_database_not_allowed_before_connecting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = FakeDatabase(ROWS)

    _error(
        tmp_path,
        capsys,
        "database_not_allowed",
        db=db,
        settings=FakeSettings(allowlist="other:5432/x"),
    )

    assert not db.connected


def test_seed_unreadable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths: dict[str, str | None] = dict(files(tmp_path))
    paths["seed"] = str(tmp_path / "missing.yaml")

    error = _error(tmp_path, capsys, "seed_unreadable", paths)

    assert error["seed"] == str(tmp_path / "missing.yaml")


def test_seed_invalid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths: dict[str, str | None] = dict(
        files(tmp_path, seed="version: 1\ntables:\n  - name: unknown\n    rows: []\n")
    )

    error = _error(tmp_path, capsys, "seed_invalid", paths)

    assert "forge validate-seed --seed" in error["message"]


def test_accepted_seed_invalid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    accepted = "version: 1\ntables:\n  - name: unknown\n    rows: []\n"

    _error(tmp_path, capsys, "accepted_seed_invalid", dict(files(tmp_path, accepted=accepted)))


def test_model_unreadable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths: dict[str, str | None] = dict(files(tmp_path))
    paths["model"] = str(tmp_path / "missing-model.yaml")

    _error(tmp_path, capsys, "model_unreadable", paths)


def test_model_invalid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths: dict[str, str | None] = dict(files(tmp_path))
    (tmp_path / "model.yaml").write_text("version: 1\ntables: 5\n", encoding="utf-8")

    _error(tmp_path, capsys, "model_invalid", paths)


def test_changelog_unreadable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _error(tmp_path, capsys, "changelog_unreadable", changesets=FakeChangesets(readable=False))


def test_accepted_root_invalid(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FORGE_ACCEPTED_DIR", "../outside")

    code = main(["reconcile-seed", "--seed", "s.yaml", "--changelog", "c.yaml"])

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["kind"] == "accepted_root_invalid"


def test_missing_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("FORGE_DB_USER", raising=False)

    code = main(
        [
            "reconcile-seed",
            "--seed",
            "s.yaml",
            "--changelog",
            "c.yaml",
            "--accepted-seed",
            "a.yaml",
            "--model",
            "m.yaml",
        ]
    )

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["kind"] == "settings_unavailable"


def test_database_outside_allowlist(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in {
        "FORGE_DB_HOST": "prod-db",
        "FORGE_DB_PORT": "5432",
        "FORGE_DB_NAME": "forge",
        "FORGE_DB_USER": "forge",
        "FORGE_DB_PASSWORD": "secret",
        "FORGE_TEST_DB_ALLOWLIST": "lbfr-db:5432/forge",
    }.items():
        monkeypatch.setenv(name, value)

    code = main(
        [
            "reconcile-seed",
            "--seed",
            "s.yaml",
            "--changelog",
            "c.yaml",
            "--accepted-seed",
            "a.yaml",
            "--model",
            "m.yaml",
        ]
    )

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["kind"] == "database_not_allowed"


def test_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["reconcile-seed", "--seed", "s.yaml"])

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["kind"] == "usage"
