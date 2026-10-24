"""Скрипт окружения интеграционных тестов в CI `tools/ci/integration-env.sh`.

Скрипт исполняется через `sh` во временном каталоге с копией `.env.example`, а `docker`, `sudo`
и `python3` в `PATH` подменяют заглушки — как в тесте гейта задач релизного сценария. Заглушка
`sudo` пишет строку hosts в файл вместо `/etc/hosts`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "ci" / "integration-env.sh"
ENV_EXAMPLE = ROOT / ".env.example"

# docker: версия Compose из COMPOSE_VERSION, ps -q — идентификатор контейнера lbfr-db-test, inspect
# по нему — две сети контейнера, остальное — в журнал
DOCKER_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_DIR/docker-calls"
case "$*" in
    "compose version --short") echo "${COMPOSE_VERSION:-2.29.1}" ;;
    "compose ps -q lbfr-db-test") echo 4a1f0c9e ;;
    "inspect "*" 4a1f0c9e")
        printf "%s\\n" "x_default 172.18.0.5" "liquibase-forge_lbfr-net 172.19.0.3" ;;
esac
exit 0
"""

SUDO_STUB = """#!/bin/sh
cat >> "$STUB_DIR/hosts"
"""

# Утилиты, которые нужны скрипту помимо заглушек. PATH собирается только из них: на машине CI
# в /usr/bin есть настоящий docker, и тест отсутствия Docker нашёл бы его
TOOLS = ("sed", "tail", "od", "tr", "basename", "dirname", "mkdir", "cat", "awk", "nohup", "sleep")
SH = shutil.which("sh") or "/bin/sh"

# python3: запуск раннера пишет в журнал и завершается, проба отвечает кодом из PROBE_CODE
PYTHON_STUB = """#!/bin/sh
if [ "$1" = -c ]; then exit "${PROBE_CODE:-0}"; fi
echo "runner $*" >> "$STUB_DIR/python-calls"
"""


def _run(
    tmp_path: Path, *, docker: bool = True, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stubs = {"sudo": SUDO_STUB, "python3": PYTHON_STUB}
    if docker:
        stubs["docker"] = DOCKER_STUB
    for name, text in stubs.items():
        (bin_dir / name).write_text(text)
        (bin_dir / name).chmod(0o755)
    for tool in TOOLS:
        found = shutil.which(tool)
        assert found is not None, tool
        (bin_dir / tool).symlink_to(found)
    work = tmp_path / "work"
    work.mkdir()
    shutil.copy(ENV_EXAMPLE, work / ".env.example")
    (tmp_path / "github_env").write_text("")
    return subprocess.run(
        [SH, str(SCRIPT)],
        cwd=work,
        env={
            "PATH": str(bin_dir),
            "STUB_DIR": str(tmp_path),
            "GITHUB_ENV": str(tmp_path / "github_env"),
            "RUNNER_WAIT": "2",
            **(extra_env or {}),
        },
        capture_output=True,
        text=True,
        check=False,
    )


def _pairs(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def test_env_file_has_one_time_token_and_local_runner(tmp_path: Path) -> None:
    result = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    env = _pairs(tmp_path / "work" / ".env")
    assert len(env["AGENT_RUNNER_TOKEN"]) == 64
    assert env["AGENT_RUNNER_URL"] == f"http://127.0.0.1:{env['AGENT_RUNNER_PORT']}"
    assert env["AGENT_RUNNER_BIND"] == "127.0.0.1"
    assert env["FORGE_TEST_DB_HOST"] == "lbfr-db-test"


def test_token_is_masked(tmp_path: Path) -> None:
    result = _run(tmp_path)

    token = _pairs(tmp_path / "work" / ".env")["AGENT_RUNNER_TOKEN"]
    assert f"::add-mask::{token}" in result.stdout.splitlines()


def test_hosts_line_uses_lbfr_net_address(tmp_path: Path) -> None:
    _run(tmp_path)

    assert (tmp_path / "hosts").read_text() == "172.19.0.3 lbfr-db-test\n"


def test_container_prefix_is_set_for_ci(tmp_path: Path) -> None:
    result = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert _pairs(tmp_path / "work" / ".env")["LBFR_CONTAINER_PREFIX"] == "lbfr-ci"


def test_container_is_found_by_service(tmp_path: Path) -> None:
    _run(tmp_path)

    calls = (tmp_path / "docker-calls").read_text().splitlines()
    assert "compose ps -q lbfr-db-test" in calls
    inspect = [call for call in calls if call.startswith("inspect ")]
    assert len(inspect) == 1
    assert inspect[0].endswith(" 4a1f0c9e")


def test_services_and_runner_are_started(tmp_path: Path) -> None:
    _run(tmp_path)

    calls = (tmp_path / "docker-calls").read_text().splitlines()
    assert "compose pull lbfr-db-test" in calls
    assert "compose --profile tools build lbfr-liquibase" in calls
    assert "compose up -d --wait lbfr-db-test" in calls
    assert not any("lbfr-db " in call or call.endswith("lbfr-db") for call in calls)
    runner = (tmp_path / "python-calls").read_text()
    assert "tools/host-runner/runner.py" in runner


def test_variables_for_next_steps(tmp_path: Path) -> None:
    _run(tmp_path)

    exported = _pairs(tmp_path / "github_env")
    env = _pairs(tmp_path / "work" / ".env")
    assert exported["FORGE_REQUIRE_INTEGRATION"] == "1"
    assert exported["AGENT_RUNNER_TOKEN"] == env["AGENT_RUNNER_TOKEN"]
    assert exported["AGENT_RUNNER_URL"] == env["AGENT_RUNNER_URL"]
    for name in ("HOST", "PORT", "NAME", "USER", "PASSWORD", "ALLOWLIST"):
        assert exported[f"FORGE_TEST_DB_{name}"] == env[f"FORGE_TEST_DB_{name}"]


def test_without_docker_is_environment_error(tmp_path: Path) -> None:
    result = _run(tmp_path, docker=False)

    assert result.returncode == 2
    assert "нет docker" in result.stderr
    assert not (tmp_path / "work" / ".env").exists()


def test_old_compose_is_environment_error(tmp_path: Path) -> None:
    result = _run(tmp_path, extra_env={"COMPOSE_VERSION": "2.19.0"})

    assert result.returncode == 2
    assert "2.20" in result.stderr


def test_existing_env_is_not_overwritten(tmp_path: Path) -> None:
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / ".env").write_text("AGENT_RUNNER_TOKEN=личный\n")
    shutil.copy(ENV_EXAMPLE, tmp_path / "work" / ".env.example")
    result = subprocess.run(
        [SH, str(SCRIPT)],
        cwd=tmp_path / "work",
        env={"PATH": "/usr/bin:/bin", "GITHUB_ENV": str(tmp_path / "github_env")},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert (tmp_path / "work" / ".env").read_text() == "AGENT_RUNNER_TOKEN=личный\n"


def test_silent_runner_is_failure(tmp_path: Path) -> None:
    result = _run(tmp_path, extra_env={"PROBE_CODE": "1"})

    assert result.returncode == 1
    assert "раннер не ответил" in result.stderr
    assert (tmp_path / "github_env").read_text() == ""
