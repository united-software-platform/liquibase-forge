# Design

## Context

- Агент работает в контейнере `claude` из образа kit'а: там есть Python 3.12 и `uv`, но нет
  `docker`, `make`, JRE и Liquibase. Docker-сокета у агента нет намеренно.
- На хосте работает раннер `tools/host-runner/runner.py`: по HTTP он выполняет одну цель `make`
  из белого списка, без параметров. `make` при ошибке рецепта возвращает `2` независимо от кода
  команды, а клиент `call.sh` сводит любой ненулевой исход к `1`.
- `docker-compose.yml`, `Makefile`, `.env.example` и `runner.py` — файлы поставки kit'а
  с контрольными суммами в `.sdd-kit-manifest.json`. Сервис `claude` получает `.env` через
  `env_file` и подключён к сети `default`.
- Мотивация — в [proposal.md](./proposal.md), контракт шлюза — в
  [specs/forge-liquibase-gateway/spec.md](./specs/forge-liquibase-gateway/spec.md).

## Goals / Non-Goals

**Goals:**

- Агент из своего контейнера запускает тесты, подключается к обеим БД и исполняет накат и откат
  Liquibase через раннер.
- Правки файлов kit'а минимальны и перечислены в README.

**Non-Goals:**

- Клиент шлюза на стороне `forge` (запись запроса, вызов раннера, разбор результата) — change
  `forge-migration`. Здесь шлюз проверяется своими тестами и ручным прогоном через раннер.
- Пайплайн CI.
- Поддержка в kit'е дополнительного белого списка из `.env` (`AGENT_RUNNER_EXTRA_TARGETS`) —
  отдельная задача в репозитории kit'а.

## Decisions

### Каркас пакета по контекстам

`src/forge/<контекст>/{domain,application,infrastructure}` для `modeling`, `migration`,
`reconciliation`, `operation` и общий `src/forge/cli/` (CLAR-022). Точка входа
`[project.scripts] forge = "forge.cli.main:main"`. В этом change CLI знает только общий
JSON-контракт: без команды или с неизвестной командой печатает в stdout один JSON-объект
с ошибкой и возвращает `2`. Предметные команды добавляют следующие change.

Зависимости: `PyYAML`, `psycopg[binary]` 3. Для разработки: `pytest`, `ruff`, `mypy`. В `mypy`
включён `strict`, в `ruff` — lint и format. Альтернатива `click`/`typer` отклонена: контракт
сводится к JSON в stdout, лишняя зависимость не окупается.

### Проектный Compose подключается из файла kit'а

В `docker-compose.yml` kit'а добавляется одна секция `include: [docker-compose.yaml]`. Проектный
`docker-compose.yaml` содержит:

| Сервис | Образ | Назначение | Особенности |
|--------|-------|------------|-------------|
| `lbfr-db` | `${LBFR_POSTGRES_IMAGE}` | Целевая БД операций | Том `lbfr-db-data`, `healthcheck`, `restart: unless-stopped` |
| `lbfr-db-test` | `${LBFR_POSTGRES_IMAGE}` | БД интеграционных тестов | Данные в `tmpfs`, `healthcheck`, `restart: unless-stopped` |
| `lbfr-liquibase` | `${LBFR_LIQUIBASE_IMAGE}` | Одноразовый запуск Liquibase | Профиль `tools`, `restart: "no"`, проект смонтирован только на чтение |

Порты на хост не публикуются (DOCK-008): агент и Liquibase обращаются к БД по сети Compose.
`environment` берётся из `.env` (DOCK-009). Альтернатива — переименовать файл kit'а — отклонена
в Q13: она ломает отслеживание манифестом.

Данные `lbfr-db-test` живут в `tmpfs`: каждый тест всё равно создаёт свою БД, и пересоздание
контейнера даёт чистый сервер без отдельной цели очистки.

### Две сети у БД

`lbfr-db` и `lbfr-db-test` подключены к `lbfr-net` (DOCK-003) и к `default`, а `lbfr-liquibase` —
только к `lbfr-net`. Сервис `claude` объявлен в файле kit'а, и подключаемый файл не может
переопределить его сети. Поэтому БД сами выходят в сеть `default`, общую для проекта Compose.

### Шлюз — stdlib-скрипт Python на хосте

`tools/liquibase/gateway.py <действие>` вызывается рецептами `make liquibase-update`
и `make liquibase-rollback`. Скрипт:

1. Удаляет прежний `.forge/liquibase-result.json`.
1. Читает `.forge/liquibase-request.json` и проверяет состав, путь changelog, совпадение действия
   с аргументом и перечень `FORGE_TEST_DB_ALLOWLIST`.
1. Выбирает учётные данные по хосту запроса: `FORGE_DB_HOST` даёт `FORGE_DB_USER`
   и `FORGE_DB_PASSWORD`, `FORGE_TEST_DB_HOST` — `FORGE_TEST_DB_*`. Хост, не совпавший ни с одним
   из них, даёт отказ `2`.
1. Запускает `docker compose run --rm -T` сервиса `lbfr-liquibase`. Адрес JDBC и учётные данные
   передаются переменными `LIQUIBASE_COMMAND_*` через `-e`, changelog — относительным путём
   при `--search-path` на смонтированный корень проекта.
1. Пишет результат: `request_id`, `action`, `exit_code`, `stdout`, `stderr`.

Скрипт на Python, а не на shell: JSON без `jq` не разобрать, а чистые функции проверки
тестируются `pytest` в контейнере агента без хоста. Нужен только `python3` хоста, который уже
требуется раннеру. Логика живёт в скрипте, а не в рецепте, чтобы цели укладывались в MAKE-001.

### Истинный код исхода — в файле результата

Скрипт завершается с кодом исхода, но `make` и `call.sh` его искажают: `make` превращает любую
ошибку в `2`, `call.sh` — в `1`. Поэтому потребитель шлюза опирается только на файл результата
с совпавшим `request_id`. Нет файла или чужой `request_id` — ошибка окружения.

### Белый список раннера

В `ALLOWED_TARGETS` добавляются `liquibase-update` и `liquibase-rollback`, комментарий
константы дополняется основанием. Цели не ждут терминала и завершаются сами, поэтому
однопоточному раннеру они не мешают.

### Тестовая БД на тест

Фикстура `pytest` в `tests/conftest.py` подключается к `lbfr-db-test` по `FORGE_TEST_DB_*`,
создаёт БД `t_<uuid>` и удаляет её после теста (`DROP DATABASE … WITH (FORCE)`). Тесты с БД
помечены маркером `integration`. Если `FORGE_TEST_DB_HOST` не задан, они пропускаются
с явной причиной. Если задан, но сервер недоступен, тест падает: недоступная среда не должна
выглядеть зелёным прогоном.

### Версии образов

`LBFR_POSTGRES_IMAGE=postgres:17` и `LBFR_LIQUIBASE_IMAGE=liquibase/liquibase:<тег>`. Тег — последний
стабильный на момент реализации: его существование проверяется загрузкой образа, а значение
закрепляется в `.env.example`. Драйвер PostgreSQL входит в официальный образ Liquibase.

## Risks / Trade-offs

- [Рядом лежат `docker-compose.yml` и `docker-compose.yaml`, и Compose без `-f` выбирает
  один файл по своему порядку имён. Если выбран проектный, сервис `claude` не найден] →
  Первая задача проверяет на хосте `docker compose config --services`: в выводе должны быть
  `claude`, `lbfr-db`, `lbfr-db-test`, `lbfr-liquibase`. Если выбран не тот файл, работа
  останавливается и решение о расположении проектного файла возвращается пользователю.
- [Для `include:` нужен Docker Compose 2.20 или новее] → Требование указывается в README,
  версия проверяется той же задачей.
- [Переустановка kit'а даёт конфликт по sha256 в четырёх файлах] → README перечисляет
  каждое отличие от поставки и его основание.
- [`env_file` kit'а передаёт агенту и пароли БД] → БД только тестовые, пароли не секретны
  за пределами машины. `.env` не коммитится.
- [Первый запуск загружает образ Liquibase дольше обычного] → Предел раннера 900 с этого
  хватает. README советует загрузить образы заранее командой `docker compose pull`.
- [Раннер и сессия агента читают `.env` только при старте] → README предписывает перезапускать
  оба после правки `.env`.

## Migration Plan

1. Скопировать новые переменные из `.env.example` в `.env`.
1. На хосте выполнить `docker compose up -d`: поднимутся `lbfr-db` и `lbfr-db-test`. Сервисы
   `claude` и `lbfr-liquibase` стоят под профилями и не стартуют.
1. Перезапустить раннер и сессию агента.

Откат — удалить `include:` из `docker-compose.yml` и выполнить `docker compose down -v` для
проектных сервисов. Принятого состояния у change нет.
