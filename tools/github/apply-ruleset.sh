#!/bin/sh
# Применение ruleset'а из файла репозитория к GitHub.
#
# Файл — ровно то тело, которое принимает REST API: POST /repos/{owner}/{repo}/rulesets.
# Ruleset ищется по имени из файла: нет — создаётся, есть — обновляется по id. Повторный запуск
# с тем же файлом ничего не меняет, поэтому команда одна и для включения, и для правки правил.
#
# Репозиторий берётся из `gh repo view` — тот, в каталоге которого вызван скрипт. Нужен `gh`,
# авторизованный с правом администрирования репозитория.
#
# Имя читается из файла строкой, без разбора JSON: в окружении может не оказаться ни jq,
# ни Python. Поэтому ключ name в файле стоит первым, и других ключей name до него нет.
#
# Коды возврата: 0 — применено, 1 — ошибка API, 2 — ошибка вызова или окружения.

set -u

SELF=$(basename "$0")

fail_usage() {
    echo "$SELF: $1" >&2
    echo "Использование: $SELF <файл ruleset'а>" >&2
    exit 2
}

[ "$#" -eq 1 ] || fail_usage "нужен ровно один аргумент — путь к файлу ruleset'а"
FILE=$1
[ -f "$FILE" ] && [ -r "$FILE" ] || fail_usage "файл не найден или не читается: $FILE"

NAME=$(sed -n 's/^[[:space:]]*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*$/\1/p' "$FILE" | head -n 1)
# Имя подставляется в выражение --jq, поэтому допускаются только безопасные символы.
printf '%s\n' "$NAME" | grep -Eq '^[A-Za-z0-9._-]+$' \
    || fail_usage "в файле нет ключа name из латиницы, цифр, точки, дефиса или подчёркивания: $FILE"

REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner) && [ -n "$REPO" ] \
    || { echo "$SELF: репозиторий не определён через gh repo view" >&2; exit 2; }

ID=$(gh api "repos/$REPO/rulesets" --paginate --jq ".[] | select(.name == \"$NAME\") | .id") \
    || { echo "$SELF: не удалось получить ruleset'ы $REPO" >&2; exit 1; }

if [ -z "$ID" ]; then
    gh api -X POST "repos/$REPO/rulesets" --input "$FILE" >/dev/null \
        || { echo "$SELF: не удалось создать ruleset $NAME в $REPO" >&2; exit 1; }
    echo "Ruleset $NAME создан в $REPO"
else
    gh api -X PUT "repos/$REPO/rulesets/$ID" --input "$FILE" >/dev/null \
        || { echo "$SELF: не удалось обновить ruleset $NAME ($ID) в $REPO" >&2; exit 1; }
    echo "Ruleset $NAME ($ID) обновлён в $REPO"
fi
