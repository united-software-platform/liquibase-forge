"""Сквозная проверка шлюза Liquibase: накат и откат настоящим Liquibase на сервере тестов.

Нужны нативный Liquibase с драйвером и сервер тестов; без них тесты пропускаются с причиной,
а при `FORGE_REQUIRE_INTEGRATION=1` падают.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import psycopg
import pytest

from forge.migration.application.apply_changelog.input import ApplyChangelogInput
from forge.migration.application.apply_changelog.use_case import ApplyChangelogUseCase
from forge.migration.infrastructure.liquibase_gateway import ProcessLiquibaseGateway
from forge.shared.domain.target_database import DatabaseNotAllowedError, TargetDatabase
from forge.shared.infrastructure.json_result_writer import JsonResultWriter
from forge.shared.infrastructure.settings import EnvironmentSettings
from tests.conftest import TestDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = "tests/fixtures/liquibase/gateway-probe.yaml"
# Каталоги состояния процесса тестов: их содержимое делу не мешает, и Liquibase их не касается
LOCAL = frozenset(
    {
        ".forge",
        ".git",
        ".venv",
        "backlog",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("liquibase_ready")]


def _environment(database: TestDatabase, allowlist: str | None = None) -> dict[str, str]:
    return {
        "FORGE_DB_HOST": database.host,
        "FORGE_DB_PORT": str(database.port),
        "FORGE_DB_NAME": database.name,
        "FORGE_DB_USER": database.user,
        "FORGE_DB_PASSWORD": database.password,
        "FORGE_TEST_DB_ALLOWLIST": allowlist or f"{database.host}:{database.port}/t_*",
    }


def _gateway(
    database: TestDatabase, allowlist: str | None = None
) -> tuple[ProcessLiquibaseGateway, EnvironmentSettings]:
    environment = {**os.environ, **_environment(database, allowlist)}
    settings = EnvironmentSettings(environment)
    return ProcessLiquibaseGateway(PROJECT_ROOT, settings, environment), settings


def _probe(database: TestDatabase) -> tuple[bool, int]:
    """Есть ли таблица и сколько записей changeset в журнале Liquibase."""
    with psycopg.connect(database.conninfo) as connection:
        table = connection.execute("SELECT to_regclass('public.gateway_probe')").fetchone()
        journal = connection.execute("SELECT to_regclass('public.databasechangelog')").fetchone()
        assert table is not None and journal is not None
        recorded = 0
        if journal[0] is not None:
            recorded = int(
                connection.execute(
                    "SELECT count(*) FROM databasechangelog WHERE id = 'gateway-probe-01'"
                ).fetchone()[0]
            )
    return table[0] is not None, recorded


def _tree() -> dict[str, str]:
    """Снимок файлов проекта: относительный путь — контрольная сумма."""
    snapshot: dict[str, str] = {}
    for directory, subdirectories, files in os.walk(PROJECT_ROOT):
        subdirectories[:] = [name for name in subdirectories if name not in LOCAL]
        for name in files:
            path = Path(directory) / name
            if not path.is_symlink():
                relative = path.relative_to(PROJECT_ROOT).as_posix()
                snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def test_update_then_rollback_one_changeset(test_database: TestDatabase) -> None:
    gateway, settings = _gateway(test_database)

    updated = gateway.update(CHANGELOG, settings.target())

    assert updated.exit_code == 0, updated.stderr
    assert _probe(test_database) == (True, 1)

    rolled_back = gateway.rollback(CHANGELOG, settings.target(), 1)

    assert rolled_back.exit_code == 0, rolled_back.stderr
    assert _probe(test_database) == (False, 0)


def test_master_with_relative_include_leaves_project_files_alone(
    test_database: TestDatabase, trail: Path
) -> None:
    """Master-changelog, как его пишет `forge close`: include относительен самому master."""
    changelogs = trail / "changelog"
    changelogs.mkdir()
    probe = (PROJECT_ROOT / CHANGELOG).read_text(encoding="utf-8")
    (changelogs / "probe.yaml").write_text(probe, encoding="utf-8")
    master = changelogs / "master.yaml"
    master.write_text(
        "databaseChangeLog:\n"
        "  - include:\n"
        "      file: probe.yaml\n"
        "      relativeToChangelogFile: true\n",
        encoding="utf-8",
    )
    gateway, settings = _gateway(test_database)
    before = _tree()

    updated = gateway.update(str(master), settings.target())
    rolled_back = gateway.rollback(str(master), settings.target(), 1)

    assert updated.exit_code == 0, updated.stderr
    assert rolled_back.exit_code == 0, rolled_back.stderr
    assert _probe(test_database) == (False, 0)
    assert _tree() == before


def test_database_outside_allowlist_never_reaches_liquibase(test_database: TestDatabase) -> None:
    gateway, _ = _gateway(test_database)
    _, outside = _gateway(test_database, allowlist=f"{test_database.host}:{test_database.port}/x_*")
    use_case = ApplyChangelogUseCase(outside, gateway, JsonResultWriter())

    with pytest.raises(DatabaseNotAllowedError):
        use_case.execute(ApplyChangelogInput(CHANGELOG))

    assert _probe(test_database) == (False, 0)


def test_target_is_test_database_of_shared_server(test_database: TestDatabase) -> None:
    """БД теста носит префикс `t_`: так перечень тестовых БД изолирует их на общем экземпляре."""
    _, settings = _gateway(test_database)
    target: TargetDatabase = settings.target()

    assert target.name.startswith("t_")
    settings.allowlist().require(target)
