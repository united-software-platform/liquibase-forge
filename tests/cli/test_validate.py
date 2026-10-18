"""Команда `forge validate`: сценарии спецификации `forge-data-model` через `main`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge.cli.main import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "model"


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, object]]:
    code = main(argv)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    payload = json.loads(lines[0])
    assert isinstance(payload, dict)
    return code, payload


def _validate(
    text: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[int, dict[str, object]]:
    path = tmp_path / "model.yaml"
    path.write_text(text, encoding="utf-8")
    return _run(["validate", "--model", str(path)], capsys)


def _paths(payload: dict[str, object]) -> list[tuple[str, str]]:
    violations = payload["violations"]
    assert isinstance(violations, list)
    return [(v["path"], v["code"]) for v in violations]


def _table(columns: str, key: str = "[id]", name: str = "customer") -> str:
    return f"  - name: {name}\n    columns:\n{columns}    primary_key: {key}\n"


ID = "      - {name: id, type: bigint}\n"


def _model(*tables: str) -> str:
    return "version: 1\ntables:\n" + "".join(tables)


def test_example_model_is_valid(capsys: pytest.CaptureFixture[str]) -> None:
    path = str(FIXTURES / "example.yaml")

    code, payload = _run(["validate", "--model", path], capsys)

    assert code == 0
    assert payload == {"model": path, "valid": True, "violations": []}


def test_minimal_model(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _validate("version: 1\ntables: []\n", tmp_path, capsys)

    assert (code, payload["valid"], payload["violations"]) == (0, True, [])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("version: 3\ntables: []\n", ("version", "unsupported_version")),
        (
            _model("  - name: customer\n    columns:\n" + ID),
            ("tables[0].primary_key", "missing_field"),
        ),
        (
            _model(_table(ID + "      - {name: note, type: text, nullable: 'no'}\n")),
            ("tables[0].columns[1].nullable", "wrong_kind"),
        ),
        (
            _model(_table(ID + "      - {name: note, type: string}\n")),
            ("tables[0].columns[1].length", "missing_type_parameter"),
        ),
        (
            _model(_table(ID + "      - {name: sum, type: decimal, precision: 5, scale: 6}\n")),
            ("tables[0].columns[1].scale", "type_parameter_out_of_range"),
        ),
        (
            _model(_table("      - {name: id, type: integer, length: 10}\n")),
            ("tables[0].columns[0].length", "unexpected_type_parameter"),
        ),
        (
            _model(_table("      - {name: id, type: varchar}\n")),
            ("tables[0].columns[0].type", "unknown_type"),
        ),
        (_model(_table(ID, name="Customer")), ("tables[0].name", "invalid_identifier")),
        (_model(_table(ID, name="order")), ("tables[0].name", "reserved_identifier")),
        (_model(_table(ID, name="t" * 61)), ("tables[0].name", "invalid_identifier")),
        (
            _model(_table(ID + "      - {name: xmin, type: bigint}\n")),
            ("tables[0].columns[1].name", "reserved_identifier"),
        ),
        (
            _model(_table(ID + "      - {name: code, type: text}\n" + ID)),
            ("tables[0].columns[2].name", "duplicate_name"),
        ),
        (_model(_table(ID), _table(ID)), ("tables[1].name", "duplicate_name")),
        (
            _model(_table(ID, key="[id, code]")),
            ("tables[0].primary_key[1]", "primary_key_unknown_column"),
        ),
        (
            _model(_table("      - {name: id, type: bigint, nullable: true}\n")),
            ("tables[0].columns[0].nullable", "primary_key_nullable"),
        ),
        (
            _model(_table("      - {name: id, type: bigint, default: 0}\n")),
            ("tables[0].columns[0].default", "unknown_field"),
        ),
        (
            _model(_table(ID + "      - name: note\n        type: text\n        type: uuid\n")),
            ("tables[0].columns[1].type", "duplicate_key"),
        ),
        (
            _model(_table(ID + "      - {name: note, type: string, length: true}\n")),
            ("tables[0].columns[1].length", "wrong_kind"),
        ),
    ],
)
def test_single_violation(
    text: str,
    expected: tuple[str, str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, payload = _validate(text, tmp_path, capsys)

    assert code == 1
    assert payload["valid"] is False
    assert _paths(payload) == [expected]


def test_table_without_columns(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    text = _model("  - name: customer\n    columns: []\n    primary_key: [id]\n")

    code, payload = _validate(text, tmp_path, capsys)

    assert code == 1
    assert ("tables[0].columns", "empty_columns") in _paths(payload)


def test_column_without_nullable_is_valid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _model(_table("      - {name: id, type: uuid}\n      - {name: email, type: text}\n"))

    code, _ = _validate(text, tmp_path, capsys)

    assert code == 0


def test_yaml_syntax_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _validate("version: 1\ntables: [\n", tmp_path, capsys)

    assert code == 1
    assert _paths(payload) == [("", "yaml_syntax")]
    violations = payload["violations"]
    assert isinstance(violations, list)
    assert "строка" in violations[0]["message"]


def test_violations_of_different_tables_come_together(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _model(
        _table("      - {name: id, type: bigint, default: 0}\n"),
        _table(ID, key="[id, code]", name="invoice"),
    )

    code, payload = _validate(text, tmp_path, capsys)

    assert code == 1
    assert _paths(payload) == [
        ("tables[0].columns[0].default", "unknown_field"),
        ("tables[1].primary_key[1]", "primary_key_unknown_column"),
    ]


def test_output_is_stable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "model.yaml"
    path.write_text(
        _model(_table("      - {name: Id, type: varchar}\n", key="[]"), _table(ID, name="order")),
        encoding="utf-8",
    )
    argv = ["validate", "--model", str(path)]

    outputs = []
    for _ in range(2):
        main(argv)
        outputs.append(capsys.readouterr().out)

    assert outputs[0] == outputs[1]


def test_missing_file_is_environment_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(tmp_path / "missing.yaml")

    code = main(["validate", "--model", path])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 2
    assert payload["error"]["kind"] == "model_unreadable"
    assert payload["error"]["model"] == path
    assert captured.err.startswith("forge: ")


def test_model_argument_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _run(["validate"], capsys)

    assert code == 2
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["kind"] == "usage"
    assert "--model" in error["message"]
