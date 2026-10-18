# Tasks

> **Примечание:** задачи с пометкой «хост» выполняет пользователь: в контейнере агента нет
> `docker` и `make`. Агент готовит команды и проверяет их вывод.

## 1. Каркас Python-проекта

- [x] 1.1 Создать `pyproject.toml` (Python 3.12, `PyYAML`, `psycopg[binary]` 3; dev — `pytest`,
  `ruff`, `mypy`; `[project.scripts] forge = "forge.cli.main:main"`; маркер `integration`; `mypy`
  strict) и выполнить `uv sync` — проверка: `uv.lock` создан, `uv run forge` печатает один
  JSON-объект с ошибкой и возвращает `2`
- [x] 1.2 Разложить пакет `src/forge/` по контекстам `modeling`, `migration`, `reconciliation`,
  `operation` со слоями `domain`, `application`, `infrastructure` и общим `cli` — проверка:
  `uv run mypy src`, `uv run ruff check`, `uv run ruff format --check` без замечаний
- [x] 1.3 Покрыть тестом общий JSON-контракт CLI: без команды и с неизвестной командой — один
  JSON-объект в stdout, диагностика только в stderr, код `2` — проверка: `uv run pytest` зелёный

## 2. Сервисы Compose

- [x] 2.1 Создать файл Compose инструмента `docker/lbfr/docker-compose.yaml` с `lbfr-db`, `lbfr-db-test`, `lbfr-liquibase`
  и сетью `lbfr-net` по design.md (DOCK-001..011; без `ports`, без `env_file`) и
  `docker/liquibase/Dockerfile` на базе Liquibase 5.x с драйвером PostgreSQL через `lpm` —
  проверка: файл разбирается `yaml.safe_load`, у каждого сервиса `container_name` равен имени,
  сеть объявлена и подключена, у `lbfr-liquibase` есть `build` с аргументами из `.env`
- [x] 2.2 Добавить в `.env.example` переменные `FORGE_DB_*`, `FORGE_TEST_DB_*`,
  `FORGE_TEST_DB_ALLOWLIST`, `LBFR_POSTGRES_IMAGE`, `LBFR_LIQUIBASE_BASE_IMAGE`,
  `LBFR_LIQUIBASE_POSTGRESQL_DRIVER`, `LBFR_LIQUIBASE_IMAGE` с несекретными умолчаниями,
  а в `.gitignore` — `.forge/` и `.venv/` — проверка: каждая переменная, подставляемая
  в `docker/lbfr/docker-compose.yaml`, есть в `.env.example`
- [x] 2.3 Добавить в `docker-compose.yml` kit'а секцию `include:` файла `docker/lbfr/docker-compose.yaml` с `project_directory: .` —
  проверка: остальное содержимое файла не изменилось (`git diff`)
- [x] 2.4 Через раннер выполнить `make forge-env-sync` и `make forge-env-check` — проверка:
  в `.env` есть переменные `FORGE_*` и `LBFR_*`, Compose 2.20 или новее, в списке сервисов
  `claude`, `lbfr-db`, `lbfr-db-test`, `lbfr-liquibase`. Если выбран не тот файл, работа
  останавливается и решение о расположении проектного файла возвращается пользователю
- [x] 2.5 Через раннер выполнить `make forge-env-up` — проверка: образ PostgreSQL загружен,
  образ `lbfr-liquibase` собран, `lbfr-liquibase --version` печатает `5.0.4`, `lbfr-db`
  и `lbfr-db-test` в состоянии `healthy`

## 3. Шлюз Liquibase

- [x] 3.1 Реализовать в `tools/liquibase/gateway.py` (только stdlib) разбор и проверку запроса:
  состав, действие против аргумента, путь changelog внутри проекта, число для `rollback`,
  перечень тестовых БД с подстановкой `*` — проверка: модульные тесты на каждый сценарий отказа
  из спецификации `forge-liquibase-gateway` зелёные
- [x] 3.2 Реализовать выбор учётных данных по хосту, сборку команды `docker compose run --rm -T
  lbfr-liquibase` и запись результата с удалением прежнего файла — проверка: модульные тесты
  на состав команды (без её исполнения) и на файл результата при отказе до запуска Liquibase
- [x] 3.3 Добавить в `Makefile` цели `liquibase-update` и `liquibase-rollback` с описаниями `##`
  и записью в `.PHONY` — проверка: `sh tools/make-lint/check.sh` возвращает `0` (MAKE-004)
- [x] 3.4 Дописать обе цели в `ALLOWED_TARGETS` `tools/host-runner/runner.py` и дополнить
  комментарий константы основанием — проверка: `python3 -c` с импортом модуля показывает обе
  цели в константе

- [x] 3.5 Вынести хостовые шаги подготовки в скрипты `tools/forge-env/` и цели `forge-env-sync`,
  `forge-env-check`, `forge-env-up` из белого списка раннера, а рецепты шлюза перевести
  на загрузку `.env` — проверка: `sh -n` скриптов, повторный `sync-env.sh` ничего не меняет,
  `sh tools/make-lint/check.sh` возвращает `0`, константа раннера содержит все пять новых целей

## 4. Тестовая БД на тест

- [x] 4.1 Написать фикстуру в `tests/conftest.py`: БД `t_<uuid>` в `lbfr-db-test` на тест
  с удалением после него, пропуск с причиной без `FORGE_TEST_DB_HOST`, падение при недоступном
  сервере — проверка: тест-образец с маркером `integration` создаёт таблицу в своей БД, а после
  прогона БД `t_*` на сервере не остаётся

## 5. Документация

- [x] 5.1 Дополнить `README.md` разделами о подготовке окружения (переменные, `docker compose
  up -d`, перезапуск раннера и сессии агента после правки `.env`), требованиях хоста
  (Compose 2.20 и новее, `python3`) и отличиях от поставки kit'а в четырёх файлах с основаниями —
  проверка: структура по DOC-014, ссылки на файлы репозитория относительные
- [x] 5.2 Добавить в `docs/architecture.md` раздел об окружении исполнения со схемой «агент →
  раннер → `lbfr-liquibase` → PostgreSQL», строки компонентов «раннер» и `lbfr-liquibase`
  и запись в таблицу версий — проверка: навигация и таблица версий по DOC-014, DOC-022, DOC-024

## 6. Сквозная проверка

- [x] 6.1 (хост) Запустить раннер с обновлённым белым списком, а после `forge-env-sync`
  перезапустить сессию агента — проверка: раннер отвечает на `/healthz`, цель `help`
  выполняется с `exit: 0`, в окружении агента есть `FORGE_DB_HOST`
- [x] 6.2 Написать сквозной тест шлюза (маркер `integration`, пропуск без `AGENT_RUNNER_URL`)
  на changelog из `tests/fixtures/liquibase/`: накат в БД теста, откат одного changeset, отказ
  для БД вне перечня — проверка: тест зелёный; после наката таблица и запись
  `DATABASECHANGELOG` есть, после отката таблицы нет, при отказе в результате код `2`
- [x] 6.3 Прогнать полный набор проверок: `uv run pytest`, `uv run ruff check`,
  `uv run ruff format --check`, `uv run mypy src`, `sh tools/make-lint/check.sh` — проверка:
  все команды возвращают `0`

## Workflow follow-up

- Коммит `LBFR-005` — по явному запросу пользователя (GIT-015), описание задачи подтверждается
  по GIT-010.
- Архивировать change после ревью.
- Завести в репозитории kit'а задачу на `AGENT_RUNNER_EXTRA_TARGETS`, чтобы правка белого списка
  перестала отличать проект от поставки.
- Завести в репозитории kit'а задачу на приведение имени `docker-compose.yml` к DOCK-011 либо
  на уточнение правила под многофайловую схему: отступления описаны в design.md.
