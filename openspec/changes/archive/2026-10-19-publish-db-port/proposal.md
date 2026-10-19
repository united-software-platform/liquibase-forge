# Proposal

## Why

Целевая БД операций `lbfr-db` доступна только по сети Compose: подключиться к ней с хоста
клиентом (`psql`, IDE) и посмотреть схему, которую построил и накатил Liquibase Forge, нельзя.
Нужен публикуемый на хост порт, задаваемый переменной `FORGE_DB_HOST_PORT`.

## What Changes

- Сервис `lbfr-db` в `docker/lbfr/docker-compose.yaml` публикует контейнерный порт `5432`
  на хостовый порт `${FORGE_DB_HOST_PORT}` на всех интерфейсах хоста.
- В `.env.example` в блок целевой БД добавляется `FORGE_DB_HOST_PORT` со значением из диапазона
  портов проекта; `make forge-env-sync` дописывает её в существующий `.env` без доработки.
- `make forge-env-check` сообщает об ошибке, если у `lbfr-db` не задан публикуемый порт.
- Внутренний адрес БД для агента и шлюза не меняется: `FORGE_DB_HOST=lbfr-db`,
  `FORGE_DB_PORT=5432`, `FORGE_TEST_DB_ALLOWLIST` прежние.
- Сервер интеграционных тестов `lbfr-db-test` порты на хост по-прежнему не публикует.
- Документация, утверждающая, что порты на хост не публикуются (комментарий compose-файла,
  `docs/architecture.md`), приводится к новому поведению; в `README.md` фиксируется диапазон
  портов проекта (DOCK-008) и способ подключения с хоста.
- **BREAKING** для существующих установок: после обновления в `.env` нужна переменная
  `FORGE_DB_HOST_PORT` — без `make forge-env-sync` Compose не получит хостовый порт `lbfr-db`.

## Capabilities

### New Capabilities

- `forge-environment`: окружение исполнения Liquibase Forge в Docker Compose — сервисы БД,
  их адреса внутри сети Compose и на хосте, переменные окружения и цели подготовки
  `forge-env-*`.

### Modified Capabilities

Нет: требования шлюза Liquibase (`forge-liquibase-gateway`) и остальных capability не меняются.

## Impact

- `docker/lbfr/docker-compose.yaml` — секция `ports` сервиса `lbfr-db`, комментарий файла.
- `.env.example` — переменная `FORGE_DB_HOST_PORT`.
- `tools/forge-env/check.sh` — проверка публикуемого порта `lbfr-db`.
- `README.md`, `docs/architecture.md` — описание сетей и подключения с хоста.
- Безопасность: БД с учётными данными из `.env` становится доступна из сети хоста — риск
  и его границы описаны в `design.md`.
