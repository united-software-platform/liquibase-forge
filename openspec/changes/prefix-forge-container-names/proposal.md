# Proposal

## Why

Если на одном Docker-хосте два проекта с установленным forge, окружение поднимается только в одном
из них: `make forge-env-up` во втором проекте падает с `Conflict. The container name "/lbfr-db" is
already in use` (LBFR-029, issue #21). Причина: `docker/lbfr/docker-compose.yaml` задаёт
`container_name` литералами (`lbfr-db`, `lbfr-db-test`, `lbfr-liquibase`), а имя контейнера должно
быть уникальным на весь хост. Файл же поставляется в каждый проект без изменений. Хостовый порт
`FORGE_DB_HOST_PORT=11932` тоже одинаков во всех проектах, поэтому после исправления имён второй
проект упрётся уже в порт.

## What Changes

- Имена контейнеров сервисов forge получают префикс проекта:
  `container_name: ${LBFR_CONTAINER_PREFIX}-lbfr-db`, то же для `lbfr-db-test` и `lbfr-liquibase`.
  Имена сервисов Compose не меняются: адреса внутри сети (`lbfr-db:5432`), команды
  `docker compose <команда> <сервис>` и `FORGE_TEST_DB_ALLOWLIST` остаются прежними.
- В блок `.env.example` (корневой файл и `install/blocks/env.example`) добавляется переменная
  `LBFR_CONTAINER_PREFIX` с пустым значением и комментарием.
- `make forge-env-sync` выводит префикс из имени корня проекта, если переменной в `.env` нет
  или она пустая. Заданное значение не меняется.
- `make forge-env-check` отказывает, если префикс пустой или не годится для имени контейнера.
- `make forge-env-up` до `docker compose up` проверяет, не заняты ли имена контейнеров и хостовый
  порт `lbfr-db` контейнерами другого Compose-проекта. Если заняты, завершается с понятным
  сообщением вместо ответа демона.
- `tools/ci/integration-env.sh` задаёт префикс в `.env` машины CI и находит контейнер
  `lbfr-db-test` через `docker compose ps -q`, а не по литеральному имени.
- **BREAKING** для установленных проектов: после обновления forge нужно выполнить
  `make forge-env-sync`, иначе `forge-env-check` откажет. Существующие контейнеры `lbfr-db*`
  пересоздаются под новыми именами. Данные тома `lbfr-db-data` сохраняются: имя тома
  от `container_name` не зависит.
- В `rules/docker.md` к DOCK-002 добавляется исключение для сервисов инструмента, который ставится
  в несколько проектов на одном хосте. В репозитории SDD Developer Kit заводится задача на то же
  исключение, чтобы обновление kit'а не перезаписало правку.

## Capabilities

### New Capabilities

Нет.

### Modified Capabilities

- `forge-environment`: имена контейнеров с префиксом проекта, переменная `LBFR_CONTAINER_PREFIX`
  в шаблоне окружения и её вывод в `forge-env-sync`, проверка префикса в `forge-env-check`,
  предварительная проверка конфликтов имён и порта в `forge-env-up`.

## Impact

- **Конфигурация:** `docker/lbfr/docker-compose.yaml`, `.env.example`, `install/blocks/env.example`.
- **Скрипты:** `tools/forge-env/sync-env.sh`, `tools/forge-env/check.sh`, `tools/forge-env/up.sh`,
  `tools/ci/integration-env.sh`.
- **Правила:** `rules/docker.md`, файл kit'а, его сумма в `.sdd-kit-manifest.json` разойдётся.
- **Документы:** `docs/architecture.md` (раздел «Окружение исполнения»), `docs/use-cases.md`
  (кейс про два проекта на одном хосте), `README.md` (шаг подготовки окружения).
- **Внешнее:** комментарий и закрытие issue #21, задача в репозитории
  `united-software-platform/sdd-developer-kit`.
- **Не затрагивается:** код CLI в `src/forge`. Шлюз `tools/liquibase/gateway.py` обращается
  к `lbfr-liquibase` по имени сервиса через `docker compose run`.
