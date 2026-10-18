#!/bin/sh
# Дописать в .env переменные Liquibase Forge (FORGE_*, LBFR_*) из .env.example, которых в .env
# ещё нет. Заданные пользователем значения не трогаются, повторный запуск ничего не меняет.
set -eu

if [ ! -f .env ]; then
	echo "Ошибка: нет файла .env — сначала выполните make init" >&2
	exit 1
fi

missing=""
while IFS= read -r line; do
	[ -n "$line" ] || continue
	name=${line%%=*}
	grep -q "^${name}=" .env || missing="${missing}${line}
"
done <<LINES
$(grep -E '^(FORGE|LBFR)_[A-Z0-9_]*=' .env.example)
LINES

if [ -z "$missing" ]; then
	echo "В .env уже есть все переменные Liquibase Forge"
	exit 0
fi

# Последняя строка .env может быть без перевода строки: дописанное не должно склеиться с ней
[ -z "$(tail -c 1 .env)" ] || echo >> .env
printf '\n# Liquibase Forge: добавлено make forge-env-sync из .env.example\n%s' "$missing" >> .env
echo "В .env добавлены переменные:"
printf '%s' "$missing" | sed 's/=.*//; s/^/  /'
