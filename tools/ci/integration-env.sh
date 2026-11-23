#!/bin/sh
# Окружение интеграционных тестов на машине CI: сервер PostgreSQL образа машины, инструменты mise
# и драйвер Liquibase — та же цепочка, что локально: CLI forge → нативный Liquibase → PostgreSQL.
#
# Сервер на машине CI предустановлен и выключен; скрипт запускает его службой. Пароль
# суперпользователя задаётся разовый — через локальный сокет, где суперпользователь узнаваем
# по учётной записи ОС, — и уходит тестам через $GITHUB_ENV под маской. Драйвер Liquibase
# и целевую базу готовит `forge env up`. Скрипт вызывается только из workflow checks,
# с активированным mise: локально окружение готовят задачи `mise run env-up` и `mise run forge-env-up`.
#
# Диагностика сервера и подготовки среды пишется в .forge/ci/postgresql.log — его печатает шаг
# «Журналы окружения» при сбое job'а.
#
# Коды возврата: 0 — окружение готово, 1 — сервер или подготовка среды не удались,
# 2 — ошибка вызова или окружения.
set -u

SELF=$(basename "$0")
PG_HOST=127.0.0.1
PG_PORT=5432
PG_READY_WAIT=${PG_READY_WAIT:-30}
LOG=.forge/ci/postgresql.log

fail() {
    code=$1
    shift
    echo "$SELF: $*" >&2
    [ -f "$LOG" ] && tail -n 20 "$LOG" >&2
    exit "$code"
}

# --- Предусловия -----------------------------------------------------------------------------

[ -n "${GITHUB_ENV:-}" ] || fail 2 "не задан GITHUB_ENV: скрипт работает только в GitHub Actions"
[ -f mise.toml ] || fail 2 "нет mise.toml: скрипт запускается из корня репозитория"
command -v forge >/dev/null 2>&1 || fail 2 "нет forge: скрипт запускается с активированным mise"
command -v sudo >/dev/null 2>&1 || fail 2 "нет sudo"
for tool in pg_isready psql od tr; do
    command -v "$tool" >/dev/null 2>&1 || fail 2 "нет утилиты $tool"
done
mkdir -p "$(dirname "$LOG")"

# --- Сервер PostgreSQL -----------------------------------------------------------------------

# Уже поднятым сервером служба не занимается: повторный запуск скрипта его не трогает
if ! pg_isready -h "$PG_HOST" -p "$PG_PORT" -q 2>/dev/null; then
    sudo systemctl start postgresql.service >>"$LOG" 2>&1 \
        || sudo service postgresql start >>"$LOG" 2>&1 \
        || fail 1 "сервер PostgreSQL не запущен"
fi
waited=0
until pg_isready -h "$PG_HOST" -p "$PG_PORT" -q 2>/dev/null; do
    waited=$((waited + 1))
    [ "$waited" -lt "$PG_READY_WAIT" ] || fail 1 "сервер PostgreSQL не принял подключения за $PG_READY_WAIT с"
    sleep 1
done

# Пароль разовый и живёт не дольше job'а
password=$(od -An -tx1 -N32 /dev/urandom | tr -d ' \n')
[ -n "$password" ] || fail 1 "не удалось получить пароль из /dev/urandom"
echo "::add-mask::$password"
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "ALTER USER postgres PASSWORD '$password'" \
    >>"$LOG" 2>&1 || fail 1 "не удалось задать пароль суперпользователя postgres"
PGPASSWORD="$password" psql -h "$PG_HOST" -p "$PG_PORT" -U postgres -d postgres -c 'SELECT 1' \
    >>"$LOG" 2>&1 || fail 1 "сервер PostgreSQL не принимает подключения по TCP"

# --- Драйвер Liquibase и целевая база --------------------------------------------------------

# Координаты целевой БД — из mise.toml, учётные данные — те же, что у сервера тестов
FORGE_DB_USER=postgres FORGE_DB_PASSWORD="$password" forge env up >>"$LOG" 2>&1 \
    || fail 1 "forge env up не подготовил среду"

# --- Переменные следующих шагов --------------------------------------------------------------

{
    # Сервер тестов — тот же экземпляр: его адрес и порт берут из mise.toml
    echo "FORGE_TEST_DB_USER=postgres"
    echo "FORGE_TEST_DB_PASSWORD=$password"
    # Пропуск интеграционного теста без окружения в CI — ошибка, а не зелёный прогон
    echo "FORGE_REQUIRE_INTEGRATION=1"
} >> "$GITHUB_ENV"
echo "Окружение интеграционных тестов готово"
