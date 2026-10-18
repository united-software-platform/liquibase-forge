"""Команда `forge reconcile`: коды `0`, `1`, `2` и повторяемость вывода."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from forge.cli.commands import reconcile
from forge.cli.main import main
from forge.modeling.application.load_model.use_case import LoadModelUseCase
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader
from forge.reconciliation.application.reconcile.use_case import (
    ReconcileDependencies,
    ReconcileUseCase,
)
from forge.shared.infrastructure.json_result_writer import JsonResultWriter
from tests.migration.fakes import FakeSettings
from tests.migration.models import CUSTOMER
from tests.reconciliation.fakes import EXECUTED, FakeChangesets, FakeReconcileDatabase
from tests.reconciliation.schemas import customer, schema


def _reconcile(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    db: FakeReconcileDatabase,
    model_text: str = CUSTOMER,
    changesets: FakeChangesets | None = None,
) -> tuple[int, dict[str, Any], str]:
    model = tmp_path / "model.yaml"
    model.write_text("version: 1\ntables:\n" + model_text, encoding="utf-8")
    changelog = tmp_path / "attempt-1" / "changelog.yaml"
    use_case = ReconcileUseCase(
        ReconcileDependencies(
            settings=FakeSettings(),
            models=LoadModelUseCase(YamlModelDraftReader(), DataModelFactory()),
            changesets=changesets or FakeChangesets(),
            schema=db,
            journal=db,
            writer=JsonResultWriter(),
        )
    )
    code = reconcile.run(argparse.Namespace(model=str(model), changelog=str(changelog)), use_case)
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1, "стандартный вывод — ровно один JSON-объект"
    return code, json.loads(lines[0]), out


def test_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload, _ = _reconcile(
        tmp_path, capsys, FakeReconcileDatabase(schema(customer()), EXECUTED)
    )

    assert (code, payload["verdict"], payload["discrepancies"]) == (0, "success", [])
    result = json.loads((tmp_path / "attempt-1" / "reconcile.json").read_text(encoding="utf-8"))
    assert result == payload


def test_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload, _ = _reconcile(
        tmp_path, capsys, FakeReconcileDatabase(schema(customer(key=None)), EXECUTED)
    )

    assert (code, payload["verdict"]) == (1, "failure")
    assert payload["discrepancies"][0] == {
        "kind": "primary_key_mismatch",
        "table": "customer",
        "column": None,
        "changeset": None,
        "expected": "[id]",
        "actual": "absent",
        "message": "первичный ключ таблицы customer: ожидался [id], в БД absent",
    }


def test_output_is_stable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = FakeReconcileDatabase(schema(customer(key=None)))

    _, _, first = _reconcile(tmp_path, capsys, db)
    _, _, second = _reconcile(tmp_path, capsys, db)

    assert first == second


@pytest.mark.parametrize(
    ("db", "model_text", "changesets", "kind"),
    [
        (FakeReconcileDatabase(schema(), available=False), CUSTOMER, None, "database_unavailable"),
        (
            FakeReconcileDatabase(schema()),
            CUSTOMER.replace("uuid", "varchar"),
            None,
            "model_invalid",
        ),
        (FakeReconcileDatabase(schema()), CUSTOMER, FakeChangesets(False), "changelog_unreadable"),
    ],
)
def test_environment_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    db: FakeReconcileDatabase,
    model_text: str,
    changesets: FakeChangesets | None,
    kind: str,
) -> None:
    code, payload, _ = _reconcile(tmp_path, capsys, db, model_text, changesets)

    assert (code, payload["error"]["kind"]) == (2, kind)
    assert not (tmp_path / "attempt-1" / "reconcile.json").exists()


def test_missing_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("FORGE_DB_USER", raising=False)

    code = main(["reconcile", "--model", "m.yaml", "--changelog", "c.yaml"])

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

    code = main(["reconcile", "--model", "m.yaml", "--changelog", "c.yaml"])

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["kind"] == "database_not_allowed"
