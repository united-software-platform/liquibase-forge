"""Операция seed на `lbfr-db-test`: цикл попыток, закрытие, общий `master.yaml` и отказ.

Беклог операции несёт фронтматтер шаблона `forge-seed`; команды каждой попытки — те, что называет
шаблон `forge-seed-apply`: `validate-seed`, `generate-seed`, `apply`, `reconcile-seed`, а при
`failure` — `rollback`. Принятые модель и seed CLI берёт из корня `FORGE_ACCEPTED_DIR`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import psycopg
import pytest

from forge.operation.infrastructure.accepted_state import FileAcceptedState
from tests.conftest import TestDatabase
from tests.integration.migration_support import forge, write_model
from tests.migration.operation_backlog import write_operation
from tests.operation.backlogs import set_values

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("runner_configured")]

MODEL_STAMP, SEED_STAMP = "20261024-120000", "20261025-101500"

TABLES = """
  - name: order_status
    columns:
      - {name: code, type: string, length: 32}
      - {name: title, type: text, nullable: false}
    primary_key: [code]
    unique:
      - [title]
"""

SEED = """version: 1
tables:
  - name: order_status
    rows:
      - {code: draft, title: Черновик}
      - {code: paid, title: Оплачен}
"""


def _accept_model(capsys: pytest.CaptureFixture[str], trail: Path, accepted: Path) -> None:
    """Принятое состояние модели: changelog операции модели принят и накатан через master."""
    directory = trail / "model-operation" / "attempt-1"
    directory.mkdir(parents=True)
    operation = write_operation(directory.parent, subject=MODEL_STAMP)
    model = write_model(directory / "model.yaml", TABLES)
    code, payload = forge(
        capsys,
        "generate",
        "--model", str(model),
        "--operation", str(operation),
        "--out", str(directory / "changelog.yaml"),
    )  # fmt: skip
    assert code == 0, payload
    FileAcceptedState(accepted).accept(MODEL_STAMP, str(directory))


def _seed_operation(root: Path) -> Path:
    """Беклог операции seed в режиме `auto` без согласия на удаления; след — в корне `root`.

    Фронтматтер — значения, которые пишет шаблон `forge-seed`; сам шаблон проверяют тесты
    `tests/operation/test_templates.py`, а здесь CLI `backlog` не нужен: его нет в CI.
    """
    directory = root / "forge-seed" / SEED_STAMP
    directory.mkdir(parents=True)
    path = write_operation(directory, subject=SEED_STAMP, allow_drop=False)
    text = path.read_text(encoding="utf-8").replace(
        "operation: forge-model\n", "operation: forge-seed\nkind: seed\nsources: []\n", 1
    )
    path.write_text(text, encoding="utf-8")
    return path


def _attempt(capsys: pytest.CaptureFixture[str], operation: Path, number: int, seed: str) -> Path:
    """Попытка по шаблону `forge-seed-apply`: seed, проверка, changelog данных и накат."""
    directory = operation.parent / f"attempt-{number}"
    directory.mkdir()
    (directory / "seed.yaml").write_text(seed, encoding="utf-8")
    set_values(operation, **{f"backlog__attempt_{number}": f"{directory}/tasks.md"})
    code, payload = forge(capsys, "validate-seed", "--seed", str(directory / "seed.yaml"))
    assert code == 0, payload
    code, payload = forge(
        capsys,
        "generate-seed",
        "--seed", str(directory / "seed.yaml"),
        "--operation", str(operation),
        "--out", str(directory / "changelog.yaml"),
    )  # fmt: skip
    assert code == 0, payload
    code, payload = forge(capsys, "apply", "--changelog", str(directory / "changelog.yaml"))
    assert code == 0, payload
    return directory


def _reconcile(capsys: pytest.CaptureFixture[str], directory: Path) -> int:
    code, payload = forge(
        capsys,
        "reconcile-seed",
        "--seed", str(directory / "seed.yaml"),
        "--changelog", str(directory / "changelog.yaml"),
    )  # fmt: skip
    assert code in (0, 1), payload
    return code


def _rows(target: TestDatabase) -> list[tuple[str, str]]:
    with psycopg.connect(target.conninfo) as connection:
        return connection.execute("SELECT code, title FROM order_status ORDER BY code").fetchall()


@pytest.fixture
def roots(trail: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Корень принятого состояния и корень следа операций внутри каталога теста."""
    accepted, backlog = trail / "db", trail / "backlog"
    monkeypatch.setenv("FORGE_ACCEPTED_DIR", accepted.as_posix())
    monkeypatch.setenv("BACKLOG_ROOT", backlog.as_posix())
    return accepted, backlog


def test_seed_operation_cycle_in_auto(
    capsys: pytest.CaptureFixture[str],
    trail: Path,
    target: TestDatabase,
    roots: tuple[Path, Path],
) -> None:
    accepted, backlog = roots
    _accept_model(capsys, trail, accepted)
    code, payload = forge(capsys, "apply", "--changelog", f"{accepted}/changelog/master.yaml")
    assert code == 0, payload
    operation = _seed_operation(backlog)
    code, payload = forge(capsys, "status", "--latest")
    assert (payload["operation"]["kind"], payload["operation"]["path"]) == (
        "seed",
        operation.as_posix(),
    )

    # Попытка 1: накатан seed, а ожидаемое значение испорчено — сверка даёт failure, откат
    first = _attempt(capsys, operation, 1, SEED)
    (first / "seed.yaml").write_text(SEED.replace("Оплачен", "Оплачено"), encoding="utf-8")
    assert _reconcile(capsys, first) == 1
    set_values(operation, verdict__attempt_1="failure")
    code, payload = forge(
        capsys, "rollback", "--operation", str(operation), "--attempt", "1"
    )  # fmt: skip
    assert (code, payload["verified"]) == (0, True), payload
    assert _rows(target) == []

    # Попытка 2: seed без порчи, сверка даёт success
    second = _attempt(capsys, operation, 2, SEED)
    assert _reconcile(capsys, second) == 0
    set_values(operation, verdict__attempt_2="success")

    code, payload = forge(capsys, "close", "--operation", str(operation))

    assert (code, payload["operation"]["status"], payload["accepted_attempt"]) == (0, "success", 2)
    assert (accepted / "seed.yaml").read_text(encoding="utf-8") == SEED
    master = (accepted / "changelog" / "master.yaml").read_text(encoding="utf-8")
    assert master.index(f"{MODEL_STAMP}.yaml") < master.index(f"{SEED_STAMP}.yaml")

    # Сверка по принятому seed: копия вне корня, чтобы reconcile.json не лёг в корень
    check = trail / "check"
    check.mkdir()
    shutil.copyfile(accepted / "seed.yaml", check / "seed.yaml")
    shutil.copyfile(accepted / "changelog" / f"{SEED_STAMP}.yaml", check / "changelog.yaml")
    assert _reconcile(capsys, check) == 0
    assert _rows(target) == [("draft", "Черновик"), ("paid", "Оплачен")]


def test_shared_master_applies_to_empty_database(
    capsys: pytest.CaptureFixture[str],
    trail: Path,
    target: TestDatabase,
    roots: tuple[Path, Path],
) -> None:
    accepted, backlog = roots
    _accept_model(capsys, trail, accepted)
    operation = _seed_operation(backlog)
    # Changelog данных строится попыткой на схеме принятой модели, затем БД очищается
    code, payload = forge(capsys, "apply", "--changelog", f"{accepted}/changelog/master.yaml")
    assert code == 0, payload
    directory = _attempt(capsys, operation, 1, SEED)
    FileAcceptedState(accepted).accept_seed(SEED_STAMP, str(directory))
    with psycopg.connect(target.conninfo, autocommit=True) as connection:
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public")

    code, payload = forge(capsys, "apply", "--changelog", f"{accepted}/changelog/master.yaml")

    assert code == 0, payload
    check = trail / "check"
    check.mkdir()
    shutil.copyfile(accepted / "model.yaml", check / "model.yaml")
    shutil.copyfile(accepted / "changelog" / f"{MODEL_STAMP}.yaml", check / "model-changelog.yaml")
    code, payload = forge(
        capsys,
        "reconcile",
        "--model", str(check / "model.yaml"),
        "--changelog", str(check / "model-changelog.yaml"),
    )  # fmt: skip
    assert (code, payload["verdict"]) == (0, "success"), payload
    shutil.copyfile(accepted / "seed.yaml", check / "seed.yaml")
    shutil.copyfile(accepted / "changelog" / f"{SEED_STAMP}.yaml", check / "changelog.yaml")
    assert _reconcile(capsys, check) == 0
    assert _rows(target) == [("draft", "Черновик"), ("paid", "Оплачен")]


def test_abandon_seed_operation_returns_rows(
    capsys: pytest.CaptureFixture[str],
    trail: Path,
    target: TestDatabase,
    roots: tuple[Path, Path],
) -> None:
    accepted, backlog = roots
    _accept_model(capsys, trail, accepted)
    code, payload = forge(capsys, "apply", "--changelog", f"{accepted}/changelog/master.yaml")
    assert code == 0, payload
    operation = _seed_operation(backlog)
    directory = _attempt(capsys, operation, 1, SEED)
    assert _reconcile(capsys, directory) == 0
    set_values(operation, verdict__attempt_1="success")
    assert _rows(target) != []

    code, payload = forge(
        capsys, "abandon", "--operation", str(operation), "--reason", "передумал"
    )  # fmt: skip

    assert code == 0, payload
    assert (payload["operation"]["kind"], payload["operation"]["status"]) == ("seed", "abandoned")
    assert [(r["attempt"], r["verified"]) for r in payload["rollbacks"]] == [(1, True)]
    assert _rows(target) == []
    assert not (accepted / "seed.yaml").exists()
