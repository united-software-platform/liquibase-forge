"""Скрипт окружения интеграционных тестов в CI `tools/ci/integration-env.sh`.

Скрипт исполняется через `sh` во временном каталоге с копией `mise.toml`, а `sudo`, `pg_isready`,
`psql`, `forge` и `sleep` в `PATH` подменяют заглушки. Заглушка `sudo` имитирует сервер: старт
службы создаёт признак готовности, по которому отвечает `pg_isready`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "ci" / "integration-env.sh"
MISE_TOML = ROOT / "mise.toml"

PG_ISREADY_STUB = """#!/bin/sh
[ -f "$STUB_DIR/ready" ] && exit 0
exit 1
"""

# sudo: ALTER USER записывает выданный пароль (ALTER_CODE — код возврата). Старт службы
# поднимает сервер: PG_START_FAILS=1 — служба не стартует, PG_STAYS_DOWN=1 — стартует,
# но сервер готовности не подаёт
SUDO_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_DIR/sudo-calls"
case "$*" in
    "systemctl start postgresql.service" | "service postgresql start")
        [ "${PG_START_FAILS:-0}" = 1 ] && exit 1
        [ "${PG_STAYS_DOWN:-0}" = 1 ] || : > "$STUB_DIR/ready"
        ;;
    "-u postgres psql "*)
        printf '%s\\n' "$*" > "$STUB_DIR/alter"
        exit "${ALTER_CODE:-0}"
        ;;
esac
exit 0
"""

# sudo без systemd: systemctl недоступен, сервер поднимает service
SUDO_WITHOUT_SYSTEMD_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_DIR/sudo-calls"
case "$*" in
    "systemctl start postgresql.service") exit 1 ;;
    "service postgresql start") : > "$STUB_DIR/ready" ;;
    "-u postgres psql "*)
        printf '%s\\n' "$*" > "$STUB_DIR/alter"
        exit "${ALTER_CODE:-0}"
        ;;
esac
exit 0
"""

# psql: проверка TCP сверяет пароль в PGPASSWORD с заданным (TCP_CODE — код возврата)
PSQL_STUB = """#!/bin/sh
if [ "$1" = -h ]; then
    grep -q "PASSWORD '$PGPASSWORD'" "$STUB_DIR/alter" && echo matched >> "$STUB_DIR/psql-calls"
    exit "${TCP_CODE:-0}"
fi
exit 0
"""

# forge: записывает учётные данные, с которыми вызвана подготовка среды (FORGE_CODE — код возврата)
FORGE_STUB = """#!/bin/sh
[ "$1 $2" = "env up" ] || exit 127
printf '%s\\n' "$FORGE_DB_USER" "$FORGE_DB_PASSWORD" > "$STUB_DIR/forge-env"
exit "${FORGE_CODE:-0}"
"""

SLEEP_STUB = """#!/bin/sh
exit 0
"""

# Утилиты скрипта помимо заглушек. PATH собирается только из них: на машине разработчика есть
# настоящий psql и forge, и тест отсутствия утилиты нашёл бы их
TOOLS = ("od", "tr", "basename", "dirname", "tail", "mkdir", "grep")
SH = shutil.which("sh") or "/bin/sh"
STUBS = {
    "sudo": SUDO_STUB,
    "pg_isready": PG_ISREADY_STUB,
    "psql": PSQL_STUB,
    "forge": FORGE_STUB,
    "sleep": SLEEP_STUB,
}


class _Run:
    """Один прогон скрипта: его результат и файлы, которые оставили заглушки."""

    def __init__(self, result: subprocess.CompletedProcess[str], stubs: Path) -> None:
        self.result = result
        self._stubs = stubs

    @property
    def code(self) -> int:
        return self.result.returncode

    @property
    def stderr(self) -> str:
        return self.result.stderr

    def lines(self, name: str) -> list[str]:
        path = self._stubs / name
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _run(
    tmp_path: Path,
    *,
    missing: str | None = None,
    sudo: str = SUDO_STUB,
    extra_env: dict[str, str] | None = None,
    mise_toml: bool = True,
    github_env: bool = True,
    server_running: bool = False,
) -> _Run:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "sudo").write_text(sudo)
    for name, text in STUBS.items():
        if name != "sudo" and name != missing:
            (bin_dir / name).write_text(text)
    for stub in bin_dir.iterdir():
        stub.chmod(0o755)
    for tool in TOOLS:
        found = shutil.which(tool)
        assert found is not None, tool
        (bin_dir / tool).symlink_to(found)
    work = tmp_path / "work"
    work.mkdir()
    if mise_toml:
        shutil.copy(MISE_TOML, work / "mise.toml")
    if server_running:
        (tmp_path / "ready").write_text("")
    github = tmp_path / "github_env"
    github.write_text("")
    env = {
        "PATH": str(bin_dir),
        "STUB_DIR": str(tmp_path),
        "PG_READY_WAIT": "3",
        **(extra_env or {}),
    }
    if github_env:
        env["GITHUB_ENV"] = str(github)
    result = subprocess.run(
        [SH, str(SCRIPT)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return _Run(result, tmp_path)


def _exported(tmp_path: Path) -> dict[str, str]:
    pairs = [line.split("=", 1) for line in (tmp_path / "github_env").read_text().splitlines()]
    return dict(pairs)


def _password(run: _Run) -> str:
    [alter] = run.lines("alter")
    found = re.search(r"PASSWORD '([0-9a-f]{64})'$", alter)
    assert found is not None, alter
    return found.group(1)


def test_server_is_started_and_gets_one_time_password(tmp_path: Path) -> None:
    run = _run(tmp_path)

    assert (run.code, run.stderr) == (0, "")
    assert run.lines("sudo-calls") == [
        "systemctl start postgresql.service",
        f"-u postgres psql -v ON_ERROR_STOP=1 -c ALTER USER postgres PASSWORD '{_password(run)}'",
    ]


def test_without_systemd_server_is_started_by_service(tmp_path: Path) -> None:
    run = _run(tmp_path, sudo=SUDO_WITHOUT_SYSTEMD_STUB)

    assert run.code == 0
    assert run.lines("sudo-calls")[:2] == [
        "systemctl start postgresql.service",
        "service postgresql start",
    ]


def test_running_server_is_not_restarted(tmp_path: Path) -> None:
    run = _run(tmp_path, server_running=True)

    assert run.code == 0
    assert [call for call in run.lines("sudo-calls") if "start" in call] == []


def test_password_reaches_tcp_check_and_environment_preparation(tmp_path: Path) -> None:
    run = _run(tmp_path)

    assert run.lines("psql-calls") == ["matched"]
    assert run.lines("forge-env") == ["postgres", _password(run)]


def test_password_is_masked(tmp_path: Path) -> None:
    run = _run(tmp_path)

    assert f"::add-mask::{_password(run)}" in run.result.stdout.splitlines()


def test_variables_for_next_steps(tmp_path: Path) -> None:
    run = _run(tmp_path)

    assert _exported(tmp_path) == {
        "FORGE_TEST_DB_USER": "postgres",
        "FORGE_TEST_DB_PASSWORD": _password(run),
        "FORGE_REQUIRE_INTEGRATION": "1",
    }


def test_service_start_failure_is_failure(tmp_path: Path) -> None:
    run = _run(tmp_path, extra_env={"PG_START_FAILS": "1"})

    assert run.code == 1
    assert "сервер PostgreSQL не запущен" in run.stderr
    assert (tmp_path / "github_env").read_text() == ""


def test_server_never_ready_is_failure(tmp_path: Path) -> None:
    run = _run(tmp_path, extra_env={"PG_STAYS_DOWN": "1"})

    assert run.code == 1
    assert "сервер PostgreSQL не принял подключения за 3 с" in run.stderr
    assert (tmp_path / "github_env").read_text() == ""


def test_alter_user_failure_is_failure(tmp_path: Path) -> None:
    run = _run(tmp_path, extra_env={"ALTER_CODE": "1"})

    assert run.stderr == (
        "integration-env.sh: не удалось задать пароль суперпользователя postgres\n"
    )
    assert (tmp_path / "github_env").read_text() == ""


def test_tcp_check_failure_is_failure(tmp_path: Path) -> None:
    run = _run(tmp_path, extra_env={"TCP_CODE": "1"})

    assert "сервер PostgreSQL не принимает подключения по TCP" in run.stderr
    assert (tmp_path / "github_env").read_text() == ""


def test_env_up_failure_is_failure(tmp_path: Path) -> None:
    run = _run(tmp_path, extra_env={"FORGE_CODE": "1"})

    assert "forge env up не подготовил среду" in run.stderr
    assert (tmp_path / "github_env").read_text() == ""


def test_without_github_env_is_environment_error(tmp_path: Path) -> None:
    run = _run(tmp_path, github_env=False)

    assert run.code == 2
    assert "не задан GITHUB_ENV" in run.stderr


def test_outside_repository_is_environment_error(tmp_path: Path) -> None:
    run = _run(tmp_path, mise_toml=False)

    assert run.code == 2
    assert "нет mise.toml" in run.stderr


def test_without_mise_activation_is_environment_error(tmp_path: Path) -> None:
    run = _run(tmp_path, missing="forge")

    assert run.code == 2
    assert "нет forge" in run.stderr


def test_script_needs_neither_docker_nor_runner() -> None:
    assert not re.search(r"docker|runner", SCRIPT.read_text(encoding="utf-8"))
