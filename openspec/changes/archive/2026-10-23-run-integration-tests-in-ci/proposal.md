# Proposal

## Why

Workflow `checks` пропускает интеграционные тесты: им нужны PostgreSQL `lbfr-db-test`, раннер целей `make`
на хосте и образ Liquibase. Накат, откат и сверка — ядро forge — проверяются только локальным прогоном
перед слиянием, и ничто не мешает его пропустить. С защитой `main` (LBFR-020) зелёный `checks` стал
обязательным условием слияния, но интеграционных тестов в нём по-прежнему нет. Задача #7 (LBFR-019) входит
в выпуск 0.3.0.

## What Changes

- **Job `checks` перед шагом «Тесты» поднимает окружение интеграционных тестов на машине CI** (решение
  владельца) — шагом со скриптом `tools/ci/integration-env.sh`:
  - `.env` из `.env.example` с разовым токеном раннера и адресом `http://127.0.0.1:<порт>`;
  - `docker compose up -d --wait lbfr-db-test` и сборка образа `lbfr-liquibase`, как у `make forge-env-up`;
  - имя `lbfr-db-test` в `/etc/hosts` машины CI указывает на IP контейнера в сети `lbfr-net`. Тесты
    на хосте и Liquibase в контейнере обращаются к одному адресу `lbfr-db-test:5432`, и Compose проекта
    не меняется;
  - в фоне запускается настоящий `tools/host-runner/runner.py`, и скрипт ждёт, пока он ответит;
  - переменные `FORGE_TEST_DB_*`, `AGENT_RUNNER_URL`, `AGENT_RUNNER_TOKEN` уходят в окружение
    следующих шагов, токен маскируется в логе.
- **Тот же шаг `uv run pytest` исполняет и интеграционные тесты** (решение владельца). Обязательная проверка
  в ruleset остаётся одна, и выпуск через `workflow_call` автоматически зависит от интеграционных тестов.
- **Тихий пропуск невозможен.** `FORGE_REQUIRE_INTEGRATION=1` превращает пропуск интеграционных тестов
  без окружения в ошибку, и workflow задаёт его. Тесты шаблонов без CLI `backlog` плагина `formular`
  в CI по-прежнему пропускаются: плагина там нет, и это вне задачи.
- **При сбое `checks` выводит в лог журнал раннера и `docker compose logs lbfr-db-test`.**
- **Тест `tests/release/test_checks_workflow.py`:**
  - шаг подготовки окружения считается командой только для CI;
  - он стоит до шага «Тесты»;
  - `FORGE_REQUIRE_INTEGRATION` задан;
  - workflow больше не обязан молчать о `FORGE_TEST_DB_HOST` и `AGENT_RUNNER_*`.
- **`CONTRIBUTING.md`, «Проверки»:** оговорка о пропуске интеграционных тестов в CI заменяется описанием
  окружения CI и `FORGE_REQUIRE_INTEGRATION`. Шапка `checks.yml` правится так же.

## Capabilities

### New Capabilities

Нет.

### Modified Capabilities

- `forge-checks`: требование «Тесты, требующие окружения, пропускаются с причиной» меняется. Интеграционные
  тесты в workflow исполняются на поднятом окружении, их пропуск — ошибка. С причиной пропускаются только
  тесты, которым нужен CLI `backlog`.

## Impact

- **Новый файл:** `tools/ci/integration-env.sh`. Он не входит в поставку: в `delivery.txt` его нет.
- **Правки:**
  - `.github/workflows/checks.yml` — шаги подготовки окружения и вывода журналов при сбое, `env`
    шага «Тесты», шапка;
  - `tests/conftest.py`, `tests/integration/conftest.py`, `tests/integration/test_liquibase_gateway_e2e.py` —
    пропуск или ошибка по `FORGE_REQUIRE_INTEGRATION`;
  - `tests/release/test_checks_workflow.py`;
  - `CONTRIBUTING.md`.
- **Время `checks` растёт** на загрузку образа PostgreSQL, сборку образа Liquibase и сами интеграционные
  тесты. Оценка — несколько минут, фактическое время фиксируется по первому прогону PR.
- **Нужен Docker с Compose 2.20+ на `ubuntu-latest`.** Образы GitHub его содержат, на Ubuntu 26.04 это
  проверит прогон PR.
- **Зависимость:** change `protect-main-branch` уже сделал `checks` обязательной проверкой. Имя job'а не меняется,
  поэтому ruleset не правится.
