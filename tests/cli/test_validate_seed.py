"""Команда `forge validate-seed`: сценарии спецификации `forge-seed-data` через `main`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge.cli.main import main

MODEL = """version: 1
tables:
  - name: order_status
    columns:
      - {name: code, type: string, length: 32}
      - {name: title, type: text, nullable: false}
    primary_key: [code]
  - name: customer
    columns:
      - {name: id, type: bigint}
    primary_key: [id]
"""

SEED = """version: 1
tables:
  - name: order_status
    rows:
      - {code: new, title: Новый}
"""


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, object]]:
    code = main(argv)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    payload = json.loads(lines[0])
    assert isinstance(payload, dict)
    return code, payload


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _paths(payload: dict[str, object]) -> list[tuple[str, str]]:
    violations = payload["violations"]
    assert isinstance(violations, list)
    return [(v["path"], v["code"]) for v in violations]


def _error(payload: dict[str, object]) -> dict[str, object]:
    error = payload["error"]
    assert isinstance(error, dict)
    return error


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Корень проекта текущим каталогом с корнем принятого состояния по умолчанию."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FORGE_ACCEPTED_DIR", raising=False)
    return tmp_path


def test_valid_seed_by_explicit_model(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seed = _write(tmp_path / "seed.yaml", SEED)
    model = _write(tmp_path / "model.yaml", MODEL)

    code, payload = _run(["validate-seed", "--seed", seed, "--model", model], capsys)

    assert code == 0
    assert payload == {"seed": seed, "model": model, "valid": True, "violations": []}


def test_empty_seed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seed = _write(tmp_path / "seed.yaml", "version: 1\ntables: []\n")
    model = _write(tmp_path / "model.yaml", MODEL)

    code, payload = _run(["validate-seed", "--seed", seed, "--model", model], capsys)

    assert (code, payload["valid"]) == (0, True)


def test_violations_give_code_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seed = _write(
        tmp_path / "seed.yaml",
        "version: 1\ntables:\n  - name: order_status\n    rows:\n      - {title: Новый}\n"
        "  - name: order_state\n    rows: []\n",
    )
    model = _write(tmp_path / "model.yaml", MODEL)

    code, payload = _run(["validate-seed", "--seed", seed, "--model", model], capsys)

    assert (code, payload["valid"]) == (1, False)
    assert _paths(payload) == [
        ("tables[0].rows[0].code", "null_value"),
        ("tables[1].name", "unknown_table"),
    ]


def test_accepted_model_by_default(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(project / "db" / "model.yaml", MODEL)
    seed = _write(project / "seed.yaml", SEED)

    code, payload = _run(["validate-seed", "--seed", seed], capsys)

    assert (code, payload["model"], payload["valid"]) == (0, "db/model.yaml", True)


def test_accepted_root_from_environment(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FORGE_ACCEPTED_DIR", ".forge/db")
    _write(project / ".forge" / "db" / "model.yaml", MODEL)
    seed = _write(project / "seed.yaml", SEED)

    code, payload = _run(["validate-seed", "--seed", seed], capsys)

    assert (code, payload["model"]) == (0, ".forge/db/model.yaml")


def test_without_accepted_model_every_table_is_unknown(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed = _write(
        project / "seed.yaml",
        "version: 1\ntables:\n  - {name: order_status, rows: []}\n  - {name: customer, rows: []}\n",
    )

    code, payload = _run(["validate-seed", "--seed", seed], capsys)

    assert code == 1
    assert _paths(payload) == [
        ("tables[0].name", "unknown_table"),
        ("tables[1].name", "unknown_table"),
    ]


def test_invalid_accepted_root(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FORGE_ACCEPTED_DIR", "../outside")
    seed = _write(project / "seed.yaml", SEED)

    code, payload = _run(["validate-seed", "--seed", seed], capsys)

    assert (code, _error(payload)["kind"]) == (2, "accepted_root_invalid")


def test_invalid_model_is_environment_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed = _write(tmp_path / "seed.yaml", "not: a seed\n")
    model = _write(tmp_path / "model.yaml", "version: 3\ntables: []\n")

    code = main(["validate-seed", "--seed", seed, "--model", model])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 2
    assert _error(payload)["kind"] == "model_invalid"
    assert _error(payload)["model"] == model
    assert "violations" not in payload
    assert captured.err.startswith("forge: ")


def test_missing_model_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seed = _write(tmp_path / "seed.yaml", SEED)
    model = str(tmp_path / "missing.yaml")

    code, payload = _run(["validate-seed", "--seed", seed, "--model", model], capsys)

    assert (code, _error(payload)["kind"], _error(payload)["model"]) == (
        2,
        "model_unreadable",
        model,
    )


def test_missing_seed_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    model = _write(tmp_path / "model.yaml", MODEL)
    seed = str(tmp_path / "missing.yaml")

    code, payload = _run(["validate-seed", "--seed", seed, "--model", model], capsys)

    assert (code, _error(payload)["kind"], _error(payload)["seed"]) == (2, "seed_unreadable", seed)


def test_repeated_check_is_byte_equal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seed = _write(
        tmp_path / "seed.yaml",
        "version: 1\ntables:\n  - name: order_status\n    rows:\n"
        "      - {code: a, title: A}\n      - {code: a, title: B, note: x}\n",
    )
    model = _write(tmp_path / "model.yaml", MODEL)
    argv = ["validate-seed", "--seed", seed, "--model", model]

    outputs = []
    for _ in range(2):
        main(argv)
        outputs.append(capsys.readouterr().out)

    assert outputs[0] == outputs[1]
    assert '"duplicate_primary_key"' in outputs[0]


def test_seed_argument_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _run(["validate-seed"], capsys)

    assert code == 2
    assert _error(payload)["kind"] == "usage"
    assert "--seed" in str(_error(payload)["message"])
