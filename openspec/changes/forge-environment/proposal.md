# Proposal

## Why

Первая поставка Liquibase Forge реализуется пятью change, и каждому нужны одни и те же опоры:
Python-проект CLI `forge`, целевая и тестовая БД PostgreSQL и способ выполнить команду Liquibase.
В контейнере агента нет ни `docker`, ни JRE, ни Liquibase, а Docker-сокет ему намеренно
не выдаётся, поэтому без отдельного канала до контейнера Liquibase не обойдётся ни одна
команда наката и отката. Этот change закладывает окружение один раз, до первой строки
предметного кода.

## What Changes

- Каркас Python-проекта: `pyproject.toml` под `uv`, пакет `src/forge/` с модулями `modeling`,
  `migration`, `reconciliation`, `operation` (в каждом слои `domain`, `application`,
  `infrastructure`) и общим слоем `cli`; точка входа `uv run forge`; проверки `pytest`, `ruff`,
  `mypy --strict`.
- Проектный `docker-compose.yaml` с сервисами `lbfr-db` (целевая БД операций), `lbfr-db-test`
  (БД интеграционных тестов) и `lbfr-liquibase` (одноразовый контейнер Liquibase); файл kit'а
  `docker-compose.yml` подключает его через `include:`.
- Шлюз Liquibase: цели `make liquibase-update` и `liquibase-rollback`, исполняемые на хосте через
  раннер. Параметры приходят файлом запроса `.forge/liquibase-request.json`, результат уходит
  файлом `.forge/liquibase-result.json`; шлюз проверяет пути и перечень тестовых БД.
- Цели шлюза дописаны в белый список раннера `tools/host-runner/runner.py` — отличие от поставки
  kit'а, зафиксированное в README.
- Переменные `FORGE_DB_*`, `FORGE_TEST_DB_*`, `FORGE_TEST_DB_ALLOWLIST`, `LBFR_POSTGRES_IMAGE`,
  `LBFR_LIQUIBASE_IMAGE` в `.env.example`; каталог `.forge/` в `.gitignore`.
- Тестовая инфраструктура: фикстура `pytest`, создающая и удаляющая отдельную БД на каждый тест
  в `lbfr-db-test`.

## Capabilities

### New Capabilities

- `forge-liquibase-gateway`: исполнение команд Liquibase в отдельном контейнере по файлу запроса
  через раннер на хосте — состав запроса и результата, проверка путей и перечня тестовых БД,
  коды исхода.

### Modified Capabilities

Нет: требования `forge-operation` не меняются.

## Impact

- **Новые файлы:** `pyproject.toml`, `uv.lock`, `src/forge/**`, `tests/**`, `docker-compose.yaml`,
  `tools/liquibase/gateway.py`.
- **Файлы поставки kit'а** (отслеживаются `.sdd-kit-manifest.json`): `docker-compose.yml` — строка
  `include:`; `Makefile` — две цели; `tools/host-runner/runner.py` — белый список; `.env.example` —
  переменные. Переустановка kit'а даст конфликт по sha256, отличия перечислены в README.
- **Окружение:** после правки `.env` перезапускаются сессия агента и раннер; хосту нужны
  `docker compose` с поддержкой `include:` и `python3`.
- **Зависимости:** `PyYAML`, `psycopg` 3; для разработки — `pytest`, `ruff`, `mypy`.
- **Вне объёма:** команды `forge` предметных контекстов — change `forge-model-format`,
  `forge-migration`, `forge-reconciliation`, `forge-operation`.
