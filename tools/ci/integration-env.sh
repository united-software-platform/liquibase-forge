#!/bin/sh
# Окружение интеграционных тестов на машине CI: сервер БД lbfr-db-test, образ Liquibase
# и раннер целей make — та же цепочка, что локально: HTTP раннера → make → шлюз → Liquibase
# в контейнере → lbfr-db-test.
#
# Тесты идут на хосте CI, Liquibase — в контейнере сети lbfr-net, а адрес БД из фикстуры уходит
# в запрос шлюзу, поэтому обе стороны должны видеть БД по одному имени. Контейнер находит
# lbfr-db-test через DNS Compose, хост — через строку в /etc/hosts с IP контейнера в lbfr-net.
# Compose проекта при этом не меняется, порт сервера на хост не публикуется.
#
# Скрипт вызывается только из workflow checks: он пишет .env и /etc/hosts и отдаёт переменные
# следующим шагам через $GITHUB_ENV. Существующий .env он не трогает — локально окружение
# готовит make forge-env-up. Раннер остаётся работать в фоне до конца job'а; его журнал —
# в $RUNNER_LOG, его печатает шаг «Журналы окружения» при сбое.
#
# Коды возврата: 0 — окружение готово, 1 — сервис или раннер не поднялись,
# 2 — нет Docker, Compose 2.20+, .env.example или $GITHUB_ENV, либо .env уже есть.

set -u

SELF=$(basename "$0")
RUNNER_LOG=${RUNNER_LOG:-.forge/ci/runner.log}
RUNNER_WAIT=${RUNNER_WAIT:-30}

fail() {
    code=$1
    shift
    echo "$SELF: $*" >&2
    exit "$code"
}

# --- Предусловия -----------------------------------------------------------------------------

[ -n "${GITHUB_ENV:-}" ] || fail 2 "не задан GITHUB_ENV: скрипт работает только в GitHub Actions"
[ -f .env.example ] || fail 2 "нет .env.example: скрипт запускается из корня репозитория"
[ ! -e .env ] || fail 2 ".env уже существует: скрипт его не перезаписывает"
command -v docker >/dev/null 2>&1 || fail 2 "нет docker"

# Compose 2.20+ нужен для include: в файле kit'а — та же проверка, что в make forge-env-check
version=$(docker compose version --short 2>/dev/null) || fail 2 "нет плагина docker compose"
version=${version#v}
major=${version%%.*}
rest=${version#*.}
minor=${rest%%.*}
if [ "$major" -lt 2 ] || { [ "$major" -eq 2 ] && [ "$minor" -lt 20 ]; }; then
    fail 2 "Docker Compose $version, нужен 2.20 или новее для include:"
fi

# --- .env ------------------------------------------------------------------------------------

# Остальные значения .env.example подходят как есть: FORGE_TEST_DB_*, перечень тестовых БД, образы.
# Префикс имён контейнеров в шаблоне пуст, а на машине CI make forge-env-sync не запускается —
# он задаётся здесь.
# Токен разовый и живёт не дольше job'а; раннер слушает только 127.0.0.1.
env_value() {
    sed -n "s/^$1=//p" .env | tail -n 1
}

token=$(od -An -tx1 -N32 /dev/urandom | tr -d ' \n')
[ -n "$token" ] || fail 1 "не удалось получить токен раннера из /dev/urandom"
port=$(sed -n 's/^AGENT_RUNNER_PORT=//p' .env.example | tail -n 1)
[ -n "$port" ] || fail 2 "в .env.example нет AGENT_RUNNER_PORT"
url="http://127.0.0.1:$port"

sed -e "s|^AGENT_RUNNER_TOKEN=.*|AGENT_RUNNER_TOKEN=$token|" \
    -e "s|^AGENT_RUNNER_URL=.*|AGENT_RUNNER_URL=$url|" \
    -e "s|^LBFR_CONTAINER_PREFIX=.*|LBFR_CONTAINER_PREFIX=lbfr-ci|" .env.example > .env
echo "AGENT_RUNNER_BIND=127.0.0.1" >> .env
echo "::add-mask::$token"

# --- Сервер БД и образ Liquibase -------------------------------------------------------------

# Подмножество make forge-env-up: целевая БД lbfr-db тестам не нужна
docker compose pull lbfr-db-test || fail 1 "не удалось загрузить образ lbfr-db-test"
docker compose --profile tools build lbfr-liquibase || fail 1 "не удалось собрать образ lbfr-liquibase"
docker compose up -d --wait lbfr-db-test || fail 1 "сервер lbfr-db-test не поднялся"

# Контейнер ищется по сервису, а не по имени: имя несёт префикс проекта LBFR_CONTAINER_PREFIX.
# Контейнер подключён к двум сетям, поэтому сеть выбирается явно. Имя сети Compose дополняет
# именем проекта: <проект>_lbfr-net
container=$(docker compose ps -q lbfr-db-test)
[ -n "$container" ] || fail 1 "не найден контейнер сервиса lbfr-db-test"
ip=$(docker inspect -f '{{range $name, $net := .NetworkSettings.Networks}}{{$name}} {{$net.IPAddress}}{{"\n"}}{{end}}' "$container" \
    | awk '$1 ~ /(^|_)lbfr-net$/ && $2 != "" { print $2; exit }')
[ -n "$ip" ] || fail 1 "не найден IP контейнера lbfr-db-test в сети lbfr-net"
printf '%s lbfr-db-test\n' "$ip" | sudo tee -a /etc/hosts >/dev/null \
    || fail 1 "не удалось дописать lbfr-db-test в /etc/hosts: нужен sudo без пароля"
echo "lbfr-db-test → $ip"

# --- Раннер ----------------------------------------------------------------------------------

mkdir -p "$(dirname "$RUNNER_LOG")"
AGENT_RUNNER_BIND=127.0.0.1 AGENT_RUNNER_PORT=$port AGENT_RUNNER_TOKEN=$token \
    nohup python3 tools/host-runner/runner.py >"$RUNNER_LOG" 2>&1 &

# Раннер готов, когда исполняет цель help с токеном: так проверяются и порт, и токен, и make
probe='
import os, sys, urllib.request
request = urllib.request.Request(os.environ["URL"] + "/run/help",
                                 headers={"X-Runner-Token": os.environ["TOKEN"]})
try:
    with urllib.request.urlopen(request, timeout=5) as response:
        sys.exit(0 if response.read().startswith(b"exit: 0") else 1)
except Exception:
    sys.exit(1)
'
waited=0
until URL=$url TOKEN=$token python3 -c "$probe"; do
    waited=$((waited + 1))
    if [ "$waited" -ge "$RUNNER_WAIT" ]; then
        cat "$RUNNER_LOG" >&2
        fail 1 "раннер не ответил на $url за $RUNNER_WAIT с"
    fi
    sleep 1
done
echo "Раннер отвечает на $url"

# --- Переменные следующих шагов --------------------------------------------------------------

{
    # Перечень тестовых БД читает и CLI forge в процессе тестов, а не только шлюз через .env:
    # локально его даёт окружение контейнера агента
    for name in FORGE_TEST_DB_HOST FORGE_TEST_DB_PORT FORGE_TEST_DB_NAME FORGE_TEST_DB_USER \
        FORGE_TEST_DB_PASSWORD FORGE_TEST_DB_ALLOWLIST; do
        echo "$name=$(env_value "$name")"
    done
    echo "AGENT_RUNNER_URL=$url"
    echo "AGENT_RUNNER_TOKEN=$token"
    # Пропуск интеграционного теста без окружения в CI — ошибка, а не зелёный прогон
    echo "FORGE_REQUIRE_INTEGRATION=1"
} >> "$GITHUB_ENV"
echo "Окружение интеграционных тестов готово"
