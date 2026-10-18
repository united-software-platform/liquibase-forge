#!/bin/sh
# Проверить окружение Compose: версия 2.20+ (нужна для include:) и выбор файла kit'а —
# в конфигурации должны быть и сервис агента, и сервисы проекта.
set -eu

version=$(docker compose version --short)
version=${version#v}
major=${version%%.*}
rest=${version#*.}
minor=${rest%%.*}
if [ "$major" -lt 2 ] || { [ "$major" -eq 2 ] && [ "$minor" -lt 20 ]; }; then
	echo "Ошибка: Docker Compose $version, нужен 2.20 или новее для include:" >&2
	exit 1
fi
echo "Docker Compose $version"

services=$(docker compose --profile claude --profile tools config --services)
status=0
for service in claude lbfr-db lbfr-db-test lbfr-liquibase; do
	if printf '%s\n' "$services" | grep -qx "$service"; then
		echo "  сервис $service: есть"
	else
		echo "  сервис $service: НЕТ" >&2
		status=1
	fi
done
[ "$status" -eq 0 ] || echo "Ошибка: Compose выбрал не тот файл или include: не сработал" >&2
exit "$status"
