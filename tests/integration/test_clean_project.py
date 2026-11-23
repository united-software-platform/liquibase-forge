"""CLI, установленный как инструмент, в чистом проекте: среда и полный цикл операции.

Проверяет путь «поставили forge в другой проект»: CLI ставится из рабочего дерева в изолированный
каталог инструментов uv, проект — временный каталог вне workspace со своим `mise.toml`,
секретами в `.env` и собственным Python-проектом. Команды идут через активированный mise, как в
сеансе разработчика; фронтматтер беклога операции записывается помощником тестов — CLI `backlog`
для этого не нужен, его нет в CI.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from tests.conftest import TestDatabase
from tests.integration.migration_support import PROJECT_ROOT, write_model
from tests.migration.operation_backlog import write_operation
from tests.operation.backlogs import set_values

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("liquibase_ready")]

STAMP = "20261123-210000"
TABLES = """
  - name: client
    columns:
      - {name: id, type: uuid}
      - {name: email, type: string, length: 320, nullable: false}
    primary_key: [id]
"""
# Фрагмент, который README.md предлагает добавить в проект: инструменты и координаты forge
MISE_TOML = """[tools]
uv = "0.12.7"
java = "temurin-21.0.13.1+2.0.LTS"
liquibase = "5.0.4"

[env]
_.file = ".env"
FORGE_DB_HOST = "localhost"
FORGE_DB_PORT = "{port}"
FORGE_DB_NAME = "{database}"
FORGE_TEST_DB_ALLOWLIST = "localhost:{port}/{database}"
"""


@pytest.fixture(scope="module")
def tool_bin(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Каталог с исполняемым файлом `forge`, установленным из рабочего дерева как инструмент uv.

    Установка изолирована переменными uv: инструменты пользователя и его `PATH` не трогаются.
    """
    root = tmp_path_factory.mktemp("uv-tool")
    tool_dir, bin_dir = root / "tools", root / "bin"
    result = subprocess.run(
        ["uv", "tool", "install", str(PROJECT_ROOT)],
        env={
            **os.environ,
            "UV_TOOL_DIR": str(tool_dir),
            "UV_TOOL_BIN_DIR": str(bin_dir),
            "UV_NO_MODIFY_PATH": "1",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    yield bin_dir


def _files(project: Path, *excluded: str) -> set[str]:
    """Относительные пути файлов проекта вне каталогов следа, локальных файлов и `.git`."""
    return {
        path.relative_to(project).as_posix()
        for path in project.rglob("*")
        if path.is_file() and path.relative_to(project).parts[0] not in (*excluded, ".git")
    }


def test_full_cycle_in_clean_project(
    tmp_path: Path, tool_bin: Path, test_database: TestDatabase, server_objects: list
) -> None:
    suffix = uuid.uuid4().hex[:12]
    database, role = f"t_clean_{suffix}", f"t_clean_r_{suffix}"
    server_objects.append((database, role))
    password = secrets.token_urlsafe(16)
    project = tmp_path / "shop"
    project.mkdir()
    (project / "mise.toml").write_text(
        MISE_TOML.format(port=test_database.port, database=database), encoding="utf-8"
    )
    (project / ".env").write_text(
        f"FORGE_DB_USER={role}\nFORGE_DB_PASSWORD={password}\n"
        f"FORGE_DB_ADMIN_USER={test_database.user}\n"
        f"FORGE_DB_ADMIN_PASSWORD={test_database.password}\n",
        encoding="utf-8",
    )
    # Собственный Python-проект: установленному CLI он не нужен и не мешает
    (project / "pyproject.toml").write_text('[project]\nname = "shop"\n', encoding="utf-8")
    (project / "src" / "shop").mkdir(parents=True)
    (project / "src" / "shop" / "__init__.py").write_text("", encoding="utf-8")
    own = _files(project)
    environment = {
        "PATH": f"{tool_bin}{os.pathsep}{os.environ['PATH']}",
        "HOME": os.environ["HOME"],
        "MISE_TRUSTED_CONFIG_PATHS": str(project),
    }

    def forge(*arguments: str) -> tuple[int, dict[str, object]]:
        """Команда установленного CLI в проекте — через mise, как в сеансе разработчика."""
        result = subprocess.run(
            ["mise", "exec", "--", "forge", *arguments],
            cwd=project,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert len(lines) == 1, result.stdout + result.stderr
        return result.returncode, json.loads(lines[0])

    code, payload = forge("env", "up")
    assert code == 0
    assert (payload["database"], payload["driver"]) == (database, "postgresql-42.7.13.jar")
    assert (payload["role_created"], payload["database_created"]) == (True, True)

    code, payload = forge("env", "check")
    assert code == 0
    assert [check["ok"] for check in payload["checks"]] == [True, True, True, True]

    code, payload = forge("status", "--latest")
    assert (code, payload["operation"]) == (0, None)

    # Цикл операции: беклог операции и попытка — как их оставляет навык с исполнителем
    trail = project / "backlog" / "forge-model" / STAMP
    trail.mkdir(parents=True)
    operation = write_operation(trail, subject=STAMP)
    attempt = trail / "attempt-1"
    attempt.mkdir()
    model = write_model(attempt / "model.yaml", TABLES)
    changelog = attempt / "changelog.yaml"

    code, payload = forge("validate", "--model", str(model))
    assert (code, payload["valid"]) == (0, True)
    code, payload = forge(
        "generate", "--model", str(model), "--operation", str(operation), "--out", str(changelog)
    )
    assert code == 0, payload
    code, payload = forge("apply", "--changelog", str(changelog))
    assert code == 0, payload
    code, payload = forge("reconcile", "--model", str(model), "--changelog", str(changelog))
    assert (code, payload["verdict"], payload["discrepancies"]) == (0, "success", [])

    set_values(
        operation,
        verdict__attempt_1="success",
        backlog__attempt_1=f"{trail}/attempt-1/tasks.md",
        gate__close='"Попытка 1 подтверждена сверкой"',
    )
    code, payload = forge("close", "--operation", str(operation))
    assert (code, payload["operation"]["status"]) == (0, "success"), payload
    code, payload = forge("report", "--operation", str(operation))
    assert (code, payload["operation"]["status"]) == (0, "success")

    # Принятое состояние легло в проект, схема — в базу проекта на общем экземпляре
    assert (project / "db" / "model.yaml").is_file()
    assert (project / "db" / "changelog" / "master.yaml").is_file()
    with psycopg.connect(
        host=test_database.host,
        port=test_database.port,
        dbname=database,
        user=role,
        password=password,
    ) as connection:
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    assert ("client",) in tables

    # Файлы проекта при этом не тронуты: появились только след и принятое состояние
    assert _files(project, "backlog", "db", ".forge") == own
