"""Changelog данных на `lbfr-db-test`: накат всех типов, вторая попытка, откат и запасной путь."""

from __future__ import annotations

import json
import shutil
from argparse import Namespace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest

from forge.cli.commands import rollback
from forge.modeling.application.load_model.input import LoadModelInput
from forge.modeling.application.load_model.use_case import LoadModelUseCase
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.domain.identifier import TableName
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader
from forge.operation.infrastructure.accepted_state import FileAcceptedState
from forge.seeding.domain.draft import RawValue, ScalarKind
from forge.seeding.domain.factory import SeedFactory
from forge.seeding.domain.seed import Seed
from forge.seeding.domain.seed_value import SeedValue, SeedValueFactory
from forge.seeding.infrastructure.yaml_reader import YamlSeedDraftReader
from tests.conftest import TestDatabase
from tests.integration.migration_support import STAMP, forge, write_model
from tests.migration.operation_backlog import write_operation

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("runner_configured")]

FIRST, SECOND = "20261025-101500", "20261026-090000"

TABLES = """
  - name: status
    columns:
      - {name: code, type: string, length: 32}
      - {name: title, type: text, nullable: false}
    primary_key: [code]
    unique:
      - [title]
  - name: transition
    columns:
      - {name: code, type: string, length: 32}
      - {name: status_code, type: string, length: 32, nullable: false}
    primary_key: [code]
    foreign_keys:
      - columns: [status_code]
        references: {table: status, columns: [code]}
  - name: sample
    columns:
      - {name: code, type: string, length: 32}
      - {name: small, type: integer}
      - {name: big, type: bigint}
      - {name: flag, type: boolean}
      - {name: note, type: text}
      - {name: amount, type: decimal, precision: 12, scale: 2}
      - {name: starts_on, type: date}
      - {name: created_at, type: timestamp}
      - {name: valid_from, type: timestamp_tz}
      - {name: external_id, type: uuid}
    primary_key: [code]
"""

FIRST_SEED = """version: 1
tables:
  - name: status
    rows:
      - {code: open, title: Открыт}
      - {code: archived, title: Архив}
  - name: transition
    rows:
      - {code: t1, status_code: archived}
  - name: sample
    rows:
      - code: full
        small: -2147483648
        big: 9223372036854775807
        flag: true
        note: "50% {x} \\\\ строка\\nвторая"
        amount: "-12.50"
        starts_on: 2026-02-28
        created_at: "2026-03-01T10:20:30.123456"
        valid_from: "2026-03-01T10:20:30.5+03:00"
        external_id: "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
      - {code: quote, note: "O'Reilly", flag: false}
"""

# Вывод `archived`, вставка `closed` и перевод ссылки `t1`; изменение и удаление в `sample`
SECOND_SEED = """version: 1
tables:
  - name: status
    rows:
      - {code: open, title: Открыт}
      - {code: closed, title: Закрыт}
  - name: transition
    rows:
      - {code: t1, status_code: closed}
  - name: sample
    rows:
      - code: full
        small: 7
        big: 9223372036854775807
        flag: false
        note: "It's new"
        amount: "0.5"
        starts_on: 2026-02-28
        created_at: "2026-03-01T10:20:30.123456"
        valid_from: "2026-03-01T07:20:30.5Z"
        external_id: "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
"""


def _model_operation(capsys: pytest.CaptureFixture[str], trail: Path) -> Path:
    """Построить и накатить changelog модели операции `STAMP`; каталог её попытки."""
    directory = trail / "attempt-1"
    directory.mkdir()
    model = write_model(directory / "model.yaml", TABLES)
    code, payload = forge(
        capsys,
        "generate",
        "--model", str(model),
        "--accepted", str(trail / "missing.yaml"),
        "--operation", str(trail / "tasks.md"),
        "--out", str(directory / "changelog.yaml"),
    )  # fmt: skip
    assert code == 0, payload
    code, payload = forge(capsys, "apply", "--changelog", str(directory / "changelog.yaml"))
    assert code == 0, payload
    return directory


def _seed_operation(
    capsys: pytest.CaptureFixture[str],
    trail: Path,
    stamp: str,
    seed: str,
    accepted: Path,
    verdict: str = "null",
) -> Path:
    """Построить и накатить changelog данных операции seed `stamp`; каталог её попытки."""
    operation = trail / f"seed-{stamp}"
    directory = operation / "attempt-1"
    directory.mkdir(parents=True)
    shutil.copyfile(trail / "attempt-1" / "model.yaml", directory / "model.yaml")
    (directory / "seed.yaml").write_text(seed, encoding="utf-8")
    write_operation(
        operation, subject=stamp, mode="interactive", verdicts=(verdict, "null", "null")
    )
    code, payload = forge(
        capsys,
        "generate-seed",
        "--seed", str(directory / "seed.yaml"),
        "--accepted-seed", str(accepted),
        "--model", str(directory / "model.yaml"),
        "--operation", str(operation / "tasks.md"),
        "--out", str(directory / "changelog.yaml"),
    )  # fmt: skip
    assert code == 0, payload
    code, payload = forge(capsys, "apply", "--changelog", str(directory / "changelog.yaml"))
    assert code == 0, payload
    return directory


def _model(directory: Path) -> DataModel:
    loading = LoadModelUseCase(YamlModelDraftReader(), DataModelFactory())
    return loading.execute(LoadModelInput(str(directory / "model.yaml"))).model


def _seed(directory: Path) -> Seed:
    reading = YamlSeedDraftReader().read(str(directory / "seed.yaml"))
    return SeedFactory().create(_model(directory), reading.draft)


def _raw(value: Any) -> RawValue:
    """Значение из БД в виде сырого значения файла seed для нормализации по типу колонки."""
    if value is None:
        return RawValue(ScalarKind.NULL, "null")
    if isinstance(value, bool):
        return RawValue(ScalarKind.BOOLEAN, "true" if value else "false")
    if isinstance(value, int):
        return RawValue(ScalarKind.INTEGER, str(value))
    if isinstance(value, datetime) and value.tzinfo is not None:
        value = value.astimezone(UTC)
    if isinstance(value, date):
        return RawValue(ScalarKind.STRING, value.isoformat())
    return RawValue(ScalarKind.STRING, str(value))


def _rows(database: TestDatabase, model: DataModel, table: str) -> list[dict[str, SeedValue]]:
    """Строки таблицы по первичному ключу, нормализованные по типам колонок модели."""
    columns = model.table(TableName(table)).columns
    names = ", ".join(column.name.value for column in columns)
    with psycopg.connect(database.conninfo) as connection:
        rows = connection.execute(f"SELECT {names} FROM {table} ORDER BY code").fetchall()
    values = SeedValueFactory()
    normalized: list[dict[str, SeedValue]] = []
    for row in rows:
        found: dict[str, SeedValue] = {}
        for column, value in zip(columns, row, strict=True):
            result = values.create(column.type, _raw(value))
            assert isinstance(result, SeedValue), result
            found[column.name.value] = result
        normalized.append(found)
    return normalized


def _expected(seed: Seed, table: str) -> list[dict[str, SeedValue]]:
    rows = [
        {column.value: value for column, value in row.values}
        for row in seed.table(TableName(table)).rows
    ]
    return sorted(rows, key=lambda row: str(row["code"]))


def _assert_state(database: TestDatabase, directory: Path) -> None:
    seed, model = _seed(directory), _model(directory)
    for table in ("status", "transition", "sample"):
        assert _rows(database, model, table) == _expected(seed, table), table


def test_every_type_and_quote_round_trip(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    _model_operation(capsys, trail)

    first = _seed_operation(capsys, trail, FIRST, FIRST_SEED, trail / "missing-seed.yaml")

    _assert_state(target, first)
    with psycopg.connect(target.conninfo) as connection:
        row = connection.execute("SELECT note FROM sample WHERE code = 'quote'").fetchone()
    assert row == ("O'Reilly",)


def _rollback(
    capsys: pytest.CaptureFixture[str], operation: Path, master: Path
) -> tuple[int, dict[str, Any]]:
    use_case = rollback.build_use_case(accepted_master_path=str(master))
    code = rollback.run(Namespace(operation=str(operation / "tasks.md"), attempt=1), use_case)
    return code, json.loads(capsys.readouterr().out)


def _row_checks(directory: Path) -> list[tuple[str, bool]]:
    result = json.loads((directory / "rollback.json").read_text(encoding="utf-8"))
    return [(c["check"], c["passed"]) for c in result["checks"] if c["check"].startswith("row_")]


def test_second_attempt_applies_and_rolls_back(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    _model_operation(capsys, trail)
    first = _seed_operation(capsys, trail, FIRST, FIRST_SEED, trail / "missing-seed.yaml")

    second = _seed_operation(
        capsys, trail, SECOND, SECOND_SEED, first / "seed.yaml", verdict="failure"
    )
    _assert_state(target, second)

    code, payload = _rollback(capsys, second.parent, trail / "accepted" / "master.yaml")

    assert code == 0, payload
    assert (payload["action"], payload["verified"]) == ("liquibase_rollback", True)
    _assert_state(target, first)
    assert sorted(set(_row_checks(second))) == [
        ("row_absent", True),
        ("row_present", True),
        ("row_restored", True),
    ]


def test_fallback_restores_accepted_data_changelog(
    capsys: pytest.CaptureFixture[str], trail: Path, target: TestDatabase
) -> None:
    state = FileAcceptedState(trail / "accepted")
    state.accept(STAMP, str(_model_operation(capsys, trail)))
    first = _seed_operation(capsys, trail, FIRST, FIRST_SEED, trail / "missing-seed.yaml")
    files = state.accept(FIRST, str(first))
    second = _seed_operation(
        capsys, trail, SECOND, SECOND_SEED, first / "seed.yaml", verdict="failure"
    )
    with psycopg.connect(target.conninfo) as connection:
        connection.execute(
            "INSERT INTO databasechangelog (id, author, filename, dateexecuted, orderexecuted, "
            "exectype) VALUES ('foreign-01', 'someone', 'db/changelog/foreign.yaml', now(), 99, "
            "'EXECUTED')"
        )

    code, payload = _rollback(capsys, second.parent, Path(files.master))

    assert code == 0, payload
    assert (payload["action"], payload["verified"]) == ("recreate_database", True)
    _assert_state(target, first)
    assert {check for check, _ in _row_checks(second)} == {
        "row_absent",
        "row_present",
        "row_restored",
    }
    assert all(passed for _, passed in _row_checks(second))
