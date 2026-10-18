# liquibase-forge

Харнесс система управления моделями данных.

---

## Навигация

- [Назначение](#назначение)
- [Требования хоста](#требования-хоста)
- [Подготовка окружения](#подготовка-окружения)
- [Использование](#использование)
- [Проверки проекта](#проверки-проекта)
- [Отличия от поставки kit'а](#отличия-от-поставки-kitа)

---

## Назначение

Харнесс системы управления моделями данных: проект заведён в рабочем пространстве USP
как инструмент группы `toolkit`.

Как устроена система — в [docs/architecture.md](./docs/architecture.md), понятия —
в [docs/domain.md](./docs/domain.md).

---

## Требования хоста

- Docker Compose 2.20 или новее: файл kit'а `docker-compose.yml` подключает проектный
  `docker/lbfr/docker-compose.yaml` секцией `include:`, которую старые версии не знают.
- `python3`: на нём работают раннер `tools/host-runner/runner.py` и шлюз Liquibase
  `tools/liquibase/gateway.py`. Сторонние пакеты не нужны.
- Доступ в сеть при первой сборке: образ `lbfr-liquibase` загружает драйвер PostgreSQL.

---

## Подготовка окружения

Подготовку выполняют цели `make`. Они входят в белый список раннера, поэтому агент может
вызвать их сам. Вручную на хосте нужно только запустить раннер, как описано
в [tools/host-runner/README.md](./tools/host-runner/README.md).

| Цель | Что делает |
|------|------------|
| `make forge-env-sync` | Дописывает в `.env` недостающие переменные `FORGE_*` и `LBFR_*` из `.env.example`, заданные значения не трогает |
| `make forge-env-check` | Проверяет Compose 2.20+ и наличие в конфигурации сервисов `claude`, `lbfr-db`, `lbfr-db-test`, `lbfr-liquibase` |
| `make forge-env-up` | Загружает образ PostgreSQL, собирает образ `lbfr-liquibase`, поднимает `lbfr-db` и `lbfr-db-test` до `healthy` |

Сервисы `claude` и `lbfr-liquibase` стоят под профилями: `docker compose up` их не запускает.

> **Важно:** сессия агента получает `.env` только при старте, поэтому после правки `.env` её
> нужно перезапустить, иначе агент будет подключаться к БД по прежним адресам. Цели шлюза
> загружают `.env` сами и перезапуска раннера не требуют. Сам раннер перезапускается
> после смены `AGENT_RUNNER_*` и после правки белого списка в `runner.py`.

`FORGE_TEST_DB_ALLOWLIST` перечисляет БД, на которые шлюз разрешает накат и откат: записи
`хост:порт/имя` через запятую, `*` на месте имени разрешает любую БД сервера. Пустой перечень
запрещает любой запрос.

Версии Liquibase и драйвера PostgreSQL задают `LBFR_LIQUIBASE_BASE_IMAGE`
и `LBFR_LIQUIBASE_POSTGRESQL_DRIVER`. При их смене меняется и `LBFR_LIQUIBASE_IMAGE`, чтобы
Compose собрал образ заново.

> **Внимание:** Liquibase 5.x распространяется под лицензией FSL, а не Apache 2.0. FSL
> ограничивает только конкурирующее коммерческое использование Liquibase.

---

## Использование

LLM вызывает Liquibase Forge навыком `forge`:

```text
/forge Справочник клиентов: id, email, имя, дата регистрации --mode auto
```

Навык начинает операцию по намерению либо продолжает открытую, исполняет её беклог
до подтверждённой модели или трёх неудач и возвращает итоговый отчёт. При успехе модель
и changelog принимаются в `db/`; коммит делает владелец.

- **Режим.** По умолчанию `interactive`: стоп-знаки перед созданием модели, накатом
  и закрытием. `auto` заменяет их автоматическими гейтами.
- **Плагин.** Нужен плагин `backlog@formular` в области проекта:
  `claude plugin install backlog@formular`. Его CLI `backlog` появляется в `PATH` после
  перезапуска сессии агента.

Статусы, команды и отчёт описаны в [docs/operation.md](./docs/operation.md), changelog
и откат — в [docs/migration.md](./docs/migration.md), сверка —
в [docs/reconciliation.md](./docs/reconciliation.md), формат модели —
в [docs/model-format.md](./docs/model-format.md).

---

## Проверки проекта

Проверки запускаются в контейнере агента:

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy src
sh tools/make-lint/check.sh
```

Интеграционные тесты помечены маркером `integration`. Без `FORGE_TEST_DB_HOST` или без
настроенного раннера (`AGENT_RUNNER_URL`, `AGENT_RUNNER_TOKEN`) они пропускаются с причиной.
Каждый тест с БД получает на сервере `lbfr-db-test` свою БД `t_<uuid>` и удаляет её после себя.

---

## Отличия от поставки kit'а

Четыре файла поставки kit'а изменены, и их контрольные суммы расходятся
с `.sdd-kit-manifest.json`. При переустановке kit'а правки нужно перенести заново.

| Файл | Отличие | Основание |
|------|---------|-----------|
| [docker-compose.yml](./docker-compose.yml) | Секция `include:` файла [docker/lbfr/docker-compose.yaml](./docker/lbfr/docker-compose.yaml) | Окружение kit'а и инструмент lbfr описаны разными файлами: сервис агента `claude` остаётся в файле kit'а, сервисы инструмента живут в подкаталоге, и в корне Compose находит один файл |
| [Makefile](./Makefile) | Цели `liquibase-update`, `liquibase-rollback` и `forge-env-*` | Раннер исполняет только цели `make`: через них агент без Docker запускает Liquibase и готовит окружение |
| [.env.example](./.env.example) | Блоки переменных Liquibase Forge | Адреса и учётные данные БД, перечень тестовых БД, версии образов |
| [tools/host-runner/runner.py](./tools/host-runner/runner.py) | Цели шлюза и `forge-env-*` в `ALLOWED_TARGETS` | Раннер отказывает целям вне белого списка; поддержки дополнительного списка из `.env` в kit'е пока нет |
