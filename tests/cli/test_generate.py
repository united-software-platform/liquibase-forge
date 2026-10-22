"""Команда `forge generate`: сценарии требований генерации `forge-migration` через `main`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from forge.cli.main import main
from tests.migration.models import CUSTOMER, INVOICE
from tests.migration.operation_backlog import write_operation


def _model(path: Path, tables: str) -> Path:
    path.write_text("version: 1\ntables:\n" + tables, encoding="utf-8")
    return path


def _generate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    attempt: str,
    accepted: str | None = None,
    subject: str = "20261017-153000",
    mode: str = "auto",
    allow_drop: bool | None = None,
) -> tuple[int, dict[str, Any], Path]:
    operation = write_operation(tmp_path, subject=subject, mode=mode, allow_drop=allow_drop)
    model = _model(tmp_path / "model.yaml", attempt)
    accepted_path = tmp_path / "accepted.yaml"
    if accepted is not None:
        _model(accepted_path, accepted)
    out = tmp_path / "attempt-1" / "changelog.yaml"
    code = main(
        [
            "generate",
            "--model", str(model),
            "--accepted", str(accepted_path),
            "--operation", str(operation),
            "--out", str(out),
        ]
    )  # fmt: skip
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    return code, json.loads(lines[0]), out


def test_first_operation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload, out = _generate(tmp_path, capsys, CUSTOMER + INVOICE)

    assert code == 0
    assert payload["changelog"] == str(out)
    assert payload["logical_file_path"] == "db/changelog/20261017-153000.yaml"
    assert [(c["id"], c["kind"], c["table"]) for c in payload["changesets"]] == [
        ("20261017-153000-01", "create_table", "customer"),
        ("20261017-153000-02", "create_table", "invoice"),
    ]
    assert len(yaml.safe_load(out.read_text(encoding="utf-8"))["databaseChangeLog"]) == 2


def test_new_column(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    attempt = CUSTOMER.replace(
        "    primary_key", "      - {name: phone, type: text}\n    primary_key"
    )

    code, payload, _ = _generate(tmp_path, capsys, attempt, accepted=CUSTOMER)

    assert code == 0
    assert payload["changesets"] == [
        {"id": "20261017-153000-01", "kind": "add_column", "table": "customer", "column": "phone"}
    ]


def test_same_models(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload, out = _generate(tmp_path, capsys, CUSTOMER, accepted=CUSTOMER)

    assert code == 0
    assert payload["changesets"] == []
    assert yaml.safe_load(out.read_text(encoding="utf-8")) == {"databaseChangeLog": []}


WITHOUT_EMAIL = CUSTOMER.replace(
    "      - {name: email, type: string, length: 255, nullable: false}\n", ""
)


def test_removed_column_is_drop_changeset_with_consent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload, out = _generate(
        tmp_path, capsys, WITHOUT_EMAIL, accepted=CUSTOMER, allow_drop=True
    )

    assert code == 0
    assert payload["non_additive"] == []
    assert payload["changesets"] == [
        {"id": "20261017-153000-01", "kind": "drop_column", "table": "customer", "column": "email"}
    ]
    assert out.exists()


def test_drop_without_consent_in_auto_is_code_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "attempt-1" / "changelog.yaml"
    out.parent.mkdir()
    out.write_text("устаревший changelog", encoding="utf-8")

    code, payload, _ = _generate(
        tmp_path, capsys, WITHOUT_EMAIL, accepted=CUSTOMER, allow_drop=False
    )

    assert code == 2
    assert payload["error"]["kind"] == "drop_not_allowed"
    assert payload["error"]["objects"] == ["customer.email"]
    assert "/forge --mode auto --allow-drop" in payload["error"]["message"]
    assert not out.exists()


def test_legacy_backlog_without_field_refuses_drop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload, _ = _generate(tmp_path, capsys, CUSTOMER, accepted=CUSTOMER + INVOICE)

    assert code == 2
    assert (payload["error"]["kind"], payload["error"]["objects"]) == (
        "drop_not_allowed",
        ["invoice"],
    )


def test_drop_in_interactive_needs_no_consent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload, _ = _generate(
        tmp_path, capsys, CUSTOMER, accepted=CUSTOMER + INVOICE, mode="interactive"
    )

    assert code == 0
    assert [(c["kind"], c["table"]) for c in payload["changesets"]] == [("drop_table", "invoice")]


def test_refused_generation_removes_old_changelog(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "attempt-1" / "changelog.yaml"
    out.parent.mkdir()
    out.write_text("устаревший changelog", encoding="utf-8")
    attempt = CUSTOMER.replace("type: string, length: 255", "type: text")

    code, payload, _ = _generate(tmp_path, capsys, attempt, accepted=CUSTOMER)

    assert code == 1
    assert payload["changelog"] is None
    assert [(c["code"], c["table"], c["column"]) for c in payload["non_additive"]] == [
        ("column_type_changed", "customer", "email")
    ]
    assert not out.exists()


def test_several_non_additive_changes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    attempt = CUSTOMER.replace("type: string, length: 255", "type: text") + INVOICE.replace(
        "primary_key: [number]", "primary_key: [total, number]"
    )

    code, payload, _ = _generate(tmp_path, capsys, attempt, accepted=CUSTOMER + INVOICE)

    assert code == 1
    codes = [c["code"] for c in payload["non_additive"]]
    assert "column_type_changed" in codes and "primary_key_changed" in codes


def test_invalid_attempt_model(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload, out = _generate(
        tmp_path, capsys, CUSTOMER.replace("type: uuid", "type: varchar")
    )

    assert code == 1
    assert [(v["path"], v["code"]) for v in payload["violations"]] == [
        ("tables[0].columns[0].type", "unknown_type")
    ]
    assert not out.exists()


def test_broken_accepted_model(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload, out = _generate(
        tmp_path, capsys, CUSTOMER, accepted=CUSTOMER.replace("type: uuid", "type: varchar")
    )

    assert code == 2
    assert payload["error"]["kind"] == "accepted_model_invalid"
    assert not out.exists()


@pytest.mark.parametrize("subject", ["2026-10-17", "operation"])
def test_subject_is_not_stamp(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], subject: str
) -> None:
    code, payload, out = _generate(tmp_path, capsys, CUSTOMER, subject=subject)

    assert code == 2
    assert payload["error"]["kind"] == "operation_unavailable"
    assert not out.exists()


def test_missing_operation_backlog(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    model = _model(tmp_path / "model.yaml", CUSTOMER)

    code = main(
        [
            "generate",
            "--model", str(model),
            "--accepted", str(tmp_path / "accepted.yaml"),
            "--operation", str(tmp_path / "missing" / "tasks.md"),
            "--out", str(tmp_path / "changelog.yaml"),
        ]
    )  # fmt: skip

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["kind"] == "operation_unavailable"


def test_missing_attempt_model(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    operation = write_operation(tmp_path)

    code = main(
        [
            "generate",
            "--model", str(tmp_path / "model.yaml"),
            "--accepted", str(tmp_path / "accepted.yaml"),
            "--operation", str(operation),
            "--out", str(tmp_path / "changelog.yaml"),
        ]
    )  # fmt: skip

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["kind"] == "model_unreadable"


def test_regeneration_is_byte_identical(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, _, out = _generate(tmp_path, capsys, CUSTOMER + INVOICE)
    first = out.read_bytes()

    _, _, out = _generate(tmp_path, capsys, CUSTOMER + INVOICE)

    assert out.read_bytes() == first


def test_operation_argument_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["generate", "--model", "m.yaml", "--accepted", "a.yaml", "--out", "c.yaml"])

    assert code == 2
    assert "--operation" in json.loads(capsys.readouterr().out)["error"]["message"]


def _generate_from_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    accepted_dir: str,
) -> tuple[int, dict[str, Any], Path]:
    """Построить changelog без `--accepted`: принятая модель — из корня `FORGE_ACCEPTED_DIR`."""
    operation = write_operation(tmp_path, subject="20261017-153000")
    model = _model(tmp_path / "model.yaml", CUSTOMER + INVOICE)
    out = tmp_path / "attempt-1" / "changelog.yaml"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FORGE_ACCEPTED_DIR", accepted_dir)
    code = main(
        ["generate", "--model", str(model), "--operation", str(operation), "--out", str(out)]
    )
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return code, json.loads(lines[0]), out


def test_accepted_model_from_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".forge" / "db"
    root.mkdir(parents=True)
    _model(root / "model.yaml", CUSTOMER)

    code, payload, _ = _generate_from_root(tmp_path, capsys, monkeypatch, ".forge/db")

    assert code == 0
    assert [(c["kind"], c["table"]) for c in payload["changesets"]] == [("create_table", "invoice")]
    assert payload["logical_file_path"] == "db/changelog/20261017-153000.yaml"


def test_invalid_accepted_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, payload, out = _generate_from_root(tmp_path, capsys, monkeypatch, "/srv/db")

    assert code == 2
    assert "FORGE_ACCEPTED_DIR" in json.dumps(payload, ensure_ascii=False)
    assert not out.exists()
