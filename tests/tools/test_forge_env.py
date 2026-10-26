"""Окружение Liquibase Forge: имена контейнеров с префиксом проекта и шаблон `.env`.

Скрипты `tools/forge-env/` исполняются через `sh` во временном каталоге, а `docker` в `PATH`
подменяет заглушка — как в тесте окружения интеграционных тестов CI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "docker" / "lbfr" / "docker-compose.yaml"
ENV_FRAGMENT = ROOT / "install" / "blocks" / "env.example"


def _container_names(prefix: str) -> dict[str, str]:
    services = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))["services"]
    return {
        name: service["container_name"].replace("${LBFR_CONTAINER_PREFIX}", prefix)
        for name, service in services.items()
    }


def test_container_names_carry_project_prefix() -> None:
    assert _container_names("shop") == {
        "lbfr-db": "shop-lbfr-db",
        "lbfr-db-test": "shop-lbfr-db-test",
        "lbfr-liquibase": "shop-lbfr-liquibase",
    }


def test_container_names_are_not_literals() -> None:
    assert set(_container_names("crm").values()).isdisjoint(_container_names("shop").values())


def _services() -> dict[str, dict[str, object]]:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))["services"]


def test_target_database_data_is_project_directory() -> None:
    assert _services()["lbfr-db"]["volumes"] == ["./data/lbfr-db:/var/lib/postgresql/data"]


def test_named_volume_is_not_declared() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))

    assert "lbfr-db-data" not in (compose.get("volumes") or {})


def test_test_server_keeps_data_in_tmpfs() -> None:
    service = _services()["lbfr-db-test"]

    assert service["tmpfs"] == ["/var/lib/postgresql/data"]
    assert "volumes" not in service


def test_template_has_empty_container_prefix() -> None:
    lines = ENV_FRAGMENT.read_text(encoding="utf-8").splitlines()

    assert "LBFR_CONTAINER_PREFIX=" in lines
    comment = lines[lines.index("LBFR_CONTAINER_PREFIX=") - 1]
    assert comment.startswith("#")


# --- make forge-env-sync ----------------------------------------------------------------------

SYNC_SCRIPT = ROOT / "tools" / "forge-env" / "sync-env.sh"
SH = shutil.which("sh") or "/bin/sh"


def _sync(project: Path, env: str) -> subprocess.CompletedProcess[str]:
    project.mkdir(parents=True)
    shutil.copy(ROOT / ".env.example", project / ".env.example")
    (project / ".env").write_text(env, encoding="utf-8")
    return subprocess.run(
        [SH, str(SYNC_SCRIPT)],
        cwd=project,
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


def _prefix_lines(project: Path) -> list[str]:
    lines = (project / ".env").read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line.startswith("LBFR_CONTAINER_PREFIX=")]


def test_sync_derives_prefix_from_directory(tmp_path: Path) -> None:
    project = tmp_path / "My_Shop.v2"
    result = _sync(project, "AGENT_RUNNER_PORT=11900\n")

    assert result.returncode == 0, result.stderr
    assert _prefix_lines(project) == ["LBFR_CONTAINER_PREFIX=my-shop-v2"]
    assert "LBFR_CONTAINER_PREFIX" in result.stdout


def test_sync_replaces_empty_prefix_in_place(tmp_path: Path) -> None:
    project = tmp_path / "shop"
    result = _sync(project, "LBFR_CONTAINER_PREFIX=\nFORGE_DB_NAME=forge\n")

    assert result.returncode == 0, result.stderr
    assert _prefix_lines(project) == ["LBFR_CONTAINER_PREFIX=shop"]
    lines = (project / ".env").read_text(encoding="utf-8").splitlines()
    assert lines[:2] == ["LBFR_CONTAINER_PREFIX=shop", "FORGE_DB_NAME=forge"]


def test_sync_keeps_given_prefix(tmp_path: Path) -> None:
    project = tmp_path / "shop"
    result = _sync(project, "LBFR_CONTAINER_PREFIX=crm\n")

    assert result.returncode == 0, result.stderr
    assert _prefix_lines(project) == ["LBFR_CONTAINER_PREFIX=crm"]


def test_sync_refuses_when_prefix_cannot_be_derived(tmp_path: Path) -> None:
    project = tmp_path / "проект"
    result = _sync(project, "AGENT_RUNNER_PORT=11900\n")

    assert result.returncode == 1
    assert "LBFR_CONTAINER_PREFIX" in result.stderr
    assert "вручную" in result.stderr
    assert (project / ".env").read_text(encoding="utf-8") == "AGENT_RUNNER_PORT=11900\n"


def test_sync_is_idempotent(tmp_path: Path) -> None:
    project = tmp_path / "shop"
    _sync(project, "AGENT_RUNNER_PORT=11900\n")
    before = (project / ".env").read_text(encoding="utf-8")
    result = subprocess.run(
        [SH, str(SYNC_SCRIPT)], cwd=project, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert (project / ".env").read_text(encoding="utf-8") == before
    assert "уже есть все переменные" in result.stdout


# --- заглушка docker для check.sh, preflight.sh и up.sh ----------------------------------------

# Конфигурация Compose — файл config.json; docker ps отвечает файлом ps-<значение фильтра>
# (name=^/shop-lbfr-db$ → ps-shop-lbfr-db, publish=11932 → ps-11932); вызовы — в журнал
DOCKER_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_DIR/docker-calls"
case "$*" in
    "compose version --short") echo 2.29.1 ;;
    "compose --profile claude --profile tools config --services")
        printf '%s\\n' claude lbfr-db lbfr-db-test lbfr-liquibase ;;
    "compose config --format json"*) cat "$STUB_DIR/config.json" ;;
    "ps "*)
        for arg in "$@"; do
            case "$arg" in
                name=*|publish=*)
                    key=$(printf '%s' "${arg#*=}" | tr -d '^/$')
                    [ ! -f "$STUB_DIR/ps-$key" ] || cat "$STUB_DIR/ps-$key" ;;
            esac
        done ;;
esac
exit 0
"""

OWN_PROJECT = "shop"


def _stub_env(
    tmp_path: Path, *, prefix: str = "shop", port: str | None = "11932"
) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "docker").write_text(DOCKER_STUB)
    (bin_dir / "docker").chmod(0o755)
    # Скрипты разбирают конфигурацию через python3, а его нет в /usr/bin на каждой машине
    if not (bin_dir / "python3").exists():
        (bin_dir / "python3").symlink_to(sys.executable)
    ports = [{"target": 5432, "published": port}] if port else []
    config = {
        "name": OWN_PROJECT,
        "services": {
            "lbfr-db": {"container_name": f"{prefix}-lbfr-db", "ports": ports},
            "lbfr-db-test": {"container_name": f"{prefix}-lbfr-db-test"},
        },
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    return {"PATH": f"{bin_dir}:/usr/bin:/bin", "STUB_DIR": str(tmp_path)}


def _ps(tmp_path: Path, key: str, name: str, project: str, directory: str) -> None:
    (tmp_path / f"ps-{key}").write_text(f"{name}\t{project}\t{directory}\n")


def _project(tmp_path: Path) -> Path:
    """Корень проекта для up.sh: скрипт вызывает preflight.sh и создаёт data/ относительно корня."""
    project = tmp_path / "project"
    (project / "tools").mkdir(parents=True, exist_ok=True)
    link = project / "tools" / "forge-env"
    if not link.exists():
        link.symlink_to(ROOT / "tools" / "forge-env")
    return project


def _script(
    tmp_path: Path, script: str, env: dict[str, str], cwd: Path = ROOT
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [SH, str(ROOT / "tools" / "forge-env" / script)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


# --- make forge-env-check ---------------------------------------------------------------------


@pytest.mark.parametrize("prefix", ["", "My Shop", "-shop"])
def test_check_refuses_missing_or_invalid_prefix(tmp_path: Path, prefix: str) -> None:
    result = _script(tmp_path, "check.sh", _stub_env(tmp_path, prefix=prefix))

    assert result.returncode != 0
    assert "LBFR_CONTAINER_PREFIX" in result.stderr


def test_check_points_to_sync_when_prefix_is_empty(tmp_path: Path) -> None:
    result = _script(tmp_path, "check.sh", _stub_env(tmp_path, prefix=""))

    assert "make forge-env-sync" in result.stderr


def test_check_names_target_container(tmp_path: Path) -> None:
    result = _script(tmp_path, "check.sh", _stub_env(tmp_path, prefix="shop"))

    assert result.returncode == 0, result.stderr
    assert "контейнер lbfr-db: shop-lbfr-db" in result.stdout


# --- preflight.sh и make forge-env-up -----------------------------------------------------------


def test_preflight_refuses_name_taken_by_other_project(tmp_path: Path) -> None:
    env = _stub_env(tmp_path)
    _ps(tmp_path, "shop-lbfr-db", "shop-lbfr-db", "other", "/home/me/other")
    result = _script(tmp_path, "preflight.sh", env)

    assert result.returncode == 1
    assert "shop-lbfr-db" in result.stderr
    assert "/home/me/other" in result.stderr
    assert "LBFR_CONTAINER_PREFIX" in result.stderr
    calls = (tmp_path / "docker-calls").read_text()
    assert not any(word in calls for word in ("up ", "stop", "rm ", "kill"))


def test_preflight_passes_for_own_containers(tmp_path: Path) -> None:
    env = _stub_env(tmp_path)
    _ps(tmp_path, "shop-lbfr-db", "shop-lbfr-db", OWN_PROJECT, str(ROOT))
    _ps(tmp_path, "11932", "shop-lbfr-db", OWN_PROJECT, str(ROOT))
    result = _script(tmp_path, "preflight.sh", env)

    assert result.returncode == 0, result.stderr


def test_preflight_refuses_port_taken_by_other_project(tmp_path: Path) -> None:
    env = _stub_env(tmp_path)
    _ps(tmp_path, "11932", "lbfr-db", "other", "/home/me/other")
    result = _script(tmp_path, "preflight.sh", env)

    assert result.returncode == 1
    assert "11932" in result.stderr
    assert "lbfr-db проекта other" in result.stderr
    assert "FORGE_DB_HOST_PORT" in result.stderr


def test_preflight_reports_every_conflict(tmp_path: Path) -> None:
    env = _stub_env(tmp_path)
    _ps(tmp_path, "shop-lbfr-db-test", "shop-lbfr-db-test", "other", "/home/me/other")
    _ps(tmp_path, "11932", "pg", "", "")
    result = _script(tmp_path, "preflight.sh", env)

    assert result.returncode == 1
    assert "shop-lbfr-db-test" in result.stderr
    assert "pg вне Compose" in result.stderr


def test_up_stops_before_compose_up_on_conflict(tmp_path: Path) -> None:
    env = _stub_env(tmp_path)
    _ps(tmp_path, "11932", "lbfr-db", "other", "/home/me/other")
    result = _script(tmp_path, "up.sh", env, _project(tmp_path))

    assert result.returncode == 1
    calls = (tmp_path / "docker-calls").read_text().splitlines()
    assert "compose --profile tools build lbfr-liquibase" in calls
    assert not any(call.startswith("compose up") for call in calls)


def test_up_runs_preflight_before_compose_up(tmp_path: Path) -> None:
    result = _script(tmp_path, "up.sh", _stub_env(tmp_path), _project(tmp_path))

    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "docker-calls").read_text().splitlines()
    preflight = calls.index("compose config --format json lbfr-db lbfr-db-test")
    assert preflight < calls.index("compose up -d --wait lbfr-db lbfr-db-test")


def test_up_creates_target_database_data_directory(tmp_path: Path) -> None:
    project = _project(tmp_path)
    result = _script(tmp_path, "up.sh", _stub_env(tmp_path), project)

    assert result.returncode == 0, result.stderr
    assert (project / "data" / "lbfr-db").is_dir()


def test_up_keeps_existing_data(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "data" / "lbfr-db").mkdir(parents=True)
    (project / "data" / "lbfr-db" / "PG_VERSION").write_text("17\n")
    (project / "data" / "fixtures.csv").write_text("id\n1\n")
    result = _script(tmp_path, "up.sh", _stub_env(tmp_path), project)

    assert result.returncode == 0, result.stderr
    assert (project / "data" / "lbfr-db" / "PG_VERSION").read_text() == "17\n"
    assert (project / "data" / "fixtures.csv").read_text() == "id\n1\n"


def test_up_does_not_create_data_directory_on_conflict(tmp_path: Path) -> None:
    project = _project(tmp_path)
    env = _stub_env(tmp_path)
    _ps(tmp_path, "11932", "lbfr-db", "other", "/home/me/other")
    result = _script(tmp_path, "up.sh", env, project)

    assert result.returncode == 1
    assert not (project / "data").exists()
