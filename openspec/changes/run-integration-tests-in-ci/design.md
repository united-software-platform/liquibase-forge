# Design

## Context

Как интеграционные тесты работают локально:

- Тесты идут в контейнере агента, в сети Compose проекта.
- Сервер `lbfr-db-test` (PostgreSQL на `tmpfs`, без публикации порта) доступен им по имени `lbfr-db-test:5432`.
  Фикстура `test_database` (`tests/conftest.py`) создаёт на нём БД `t_<uuid>` и удаляет её после теста.
  Без `FORGE_TEST_DB_HOST` тест пропускается.
- Накат и откат идут через раннер на хосте: `AGENT_RUNNER_URL`/`AGENT_RUNNER_TOKEN`, фикстура `runner_configured`
  и проверка в `test_liquibase_gateway_e2e.py`.
  - Раннер (`tools/host-runner/runner.py`, только стандартная библиотека) исполняет `make liquibase-update`
    или `liquibase-rollback`. Рецепт загружает `./.env` и вызывает `tools/liquibase/gateway.py`.
  - Шлюз запускает `docker compose run --rm -T lbfr-liquibase` в сети `lbfr-net` и передаёт ему
    `host:port/база` из запроса, то есть тот же `lbfr-db-test:5432`.
  - Запасной путь отката пересоздаёт БД через psycopg со стороны тестов.
- Окружение поднимает `make forge-env-up` (`tools/forge-env/up.sh`): загрузка образов, сборка `lbfr-liquibase`,
  `up -d --wait`.

Workflow `checks` — один job на `ubuntu-latest` с шагами uv, `uv sync --frozen`, линтер, формат, типы,
`uv run pytest`, make-lint. Тест `test_checks_workflow.py` сверяет команды шагов с блоком «Проверки»
`CONTRIBUTING.md`, исключая команды только для CI (`CI_ONLY`).

## Goals / Non-Goals

**Goals:**

- На каждом PR и при выпуске интеграционные тесты исполняются через ту же цепочку, что локально:
  HTTP раннера → `make` → шлюз → Liquibase в контейнере → `lbfr-db-test`.
- Неподнявшееся окружение даёт красный прогон, а не зелёный с пропусками.
- Код тестов не получает веток «только для CI», кроме признака обязательности.

**Non-Goals:**

- Тесты шаблонов операций с CLI `backlog` плагина `formular`: плагина в CI нет.
- Кэширование образов Docker между прогонами. Решается позже, если время `checks` станет помехой.
- Отдельный job и изменение ruleset (решение владельца — тот же job).
- Изменение `docker/lbfr/docker-compose.yaml` и раннера.

## Decisions

**Тесты на хосте CI, имя `lbfr-db-test` через `/etc/hosts`.** Тесты и Liquibase должны видеть БД по одному
адресу: адрес из фикстуры уходит в запрос шлюзу.

- Liquibase в контейнере находит `lbfr-db-test` через DNS Compose.
- Хосту скрипт добавляет строку `<IP контейнера в lbfr-net> lbfr-db-test` в `/etc/hosts` (`sudo` на раннере
  GitHub без пароля). IP берётся из `docker inspect` по сети `lbfr-net`: контейнер подключён к двум сетям,
  поэтому сеть выбирается явно. На Linux мостовые адреса контейнеров с хоста доступны.

Отклонённые варианты:

- Публикация `5432:5432` через override-файл Compose. Шлюз вызывает `docker compose` без `-f`, поэтому
  override пришлось бы подключать через `COMPOSE_FILE` для всех команд. К тому же порт 5432 хоста мог
  быть занят.
- Тесты в контейнере на `lbfr-net`. Это отдельный образ с uv, `extra_hosts` и монтирование дерева:
  больше движущихся частей ради той же цепочки (решение владельца).

**Скрипт `tools/ci/integration-env.sh` вместо шагов YAML.** Подготовка окружения — около десяти команд
с ожиданием. В скрипте их можно проверить `sh -n` и тестом с заглушками, а шаг workflow остаётся одной
строкой `sh tools/ci/integration-env.sh`, которую тест сверки заносит в `CI_ONLY`. Порядок:

1. `.env` из `.env.example`. В нём заменяются:
   - `AGENT_RUNNER_TOKEN` — случайный из `/dev/urandom`;
   - `AGENT_RUNNER_URL=http://127.0.0.1:${AGENT_RUNNER_PORT}`;
   - `AGENT_RUNNER_BIND=127.0.0.1` — дописывается: раннер не слушает внешние интерфейсы.

   Остальные значения `.env.example` подходят как есть: `FORGE_TEST_DB_*`, перечень тестовых БД,
   образы.
1. `docker compose pull lbfr-db-test`, `docker compose --profile tools build lbfr-liquibase`,
   `docker compose up -d --wait lbfr-db-test`. Это подмножество `up.sh`: `lbfr-db` тестам не нужна.
1. Строка `/etc/hosts`.
1. `nohup python3 tools/host-runner/runner.py >"$RUNNER_LOG" 2>&1 &` с переменными из `.env`.
   Затем ожидание до 30 секунд, пока раннер не ответит на цель `help` с токеном. Процесс живёт до конца job'а.
1. Вывод в `$GITHUB_ENV`: `FORGE_TEST_DB_HOST/PORT/NAME/USER/PASSWORD`, `AGENT_RUNNER_URL`,
   `AGENT_RUNNER_TOKEN`, `FORGE_REQUIRE_INTEGRATION=1`. Токен перед этим маскируется
   (`::add-mask::`).

Коды возврата: `0` — окружение готово, `1` — сервис или раннер не поднялись (с выводом причины),
`2` — нет Docker или `.env.example`.

**`FORGE_REQUIRE_INTEGRATION` — единственная ветка для CI в тестах.** Три места, которые сейчас вызывают
`pytest.skip` из-за окружения, вызывают общий помощник из `tests/conftest.py`: при `FORGE_REQUIRE_INTEGRATION=1`
он делает `pytest.fail` с той же причиной, иначе — `pytest.skip`. Это `_server()` в `tests/conftest.py`,
`runner_configured` и проверка в `test_liquibase_gateway_e2e.py`.

- Локально поведение не меняется.
- Пропуск тестов CLI `backlog` помощника не использует.
- Признак задаёт скрипт через `$GITHUB_ENV`. Если шаг окружения упал, job остановится раньше тестов,
  а если признак не дошёл, тест сверки workflow это заметит.

**Журналы при сбое.** Последний шаг job'а с `if: failure()` печатает журнал раннера и
`docker compose logs lbfr-db-test`. Без них упавший накат в CI не разобрать.

**Сверка workflow с `CONTRIBUTING.md`.**

- `CI_ONLY` получает `sh tools/ci/integration-env.sh` и команду вывода журналов.
- Новые проверки теста:
  - шаг окружения стоит до шага «Тесты»;
  - шаг журналов идёт с `if: failure()`.
- Признак `FORGE_REQUIRE_INTEGRATION` задаёт скрипт, поэтому тест проверяет его наличие в тексте скрипта.

## Risks / Trade-offs

- [`checks` замедляется на загрузку и сборку образов] → Сборка `lbfr-liquibase` — один слой с драйвером
  поверх загруженного образа. Если время станет помехой — кэш слоёв отдельной задачей.
- [`/etc/hosts` и `sudo` есть не на каждом раннере] → `checks` идёт только на раннерах GitHub, где `sudo`
  без пароля доступен. На self-hosted скрипт падает с понятной причиной.
- [Docker или Compose на Ubuntu 26.04 окажется старше 2.20] → Скрипт проверяет версию так же, как
  `forge-env-check`, и падает с причиной. Откат — `runs-on: ubuntu-24.04`.
- [Интеграционный тест нестабилен в CI] → Падение — красный `checks`, PR не слить. Тест чинится, а не
  пропускается. Перезапуск job'а — штатная кнопка GitHub.
- [Токен раннера в логе] → Токен разовый, маскируется до вывода, раннер слушает только `127.0.0.1`
  и живёт не дольше job'а.

## Migration Plan

1. Скрипт, помощник пропуска, правка workflow и тестов, `CONTRIBUTING.md` в ветке `release/v0.3.0`.
1. Локально: полный прогон с раннером (интеграционные зелёные), прогон без окружения с
   `FORGE_REQUIRE_INTEGRATION=1` (интеграционные падают), прогон без признака (пропускаются).
1. Проверка на GitHub — прогон `checks` на PR выпуска 0.3.0 или пробный запуск `release` из ветки.
   В логе интеграционные тесты исполнены, пропусков с маркером `integration` нет.

Откат — убрать шаги из workflow. Помощник без признака ведёт себя как прежний `pytest.skip`.

## Open Questions

Нет.
