# Tasks

## 1. Признак обязательности в тестах

- [ ] 1.1 В `tests/conftest.py` — помощник «пропуск или ошибка»: при `FORGE_REQUIRE_INTEGRATION=1` — `pytest.fail` с причиной, иначе `pytest.skip`. Его вызывают `_server()`, фикстура `runner_configured` (`tests/integration/conftest.py`) и проверка раннера в `tests/integration/test_liquibase_gateway_e2e.py`. Пропуск тестов CLI `backlog` не меняется. Проверка: тест помощника для обоих значений признака; `uv run pytest -m integration` без окружения — пропуски, с `FORGE_REQUIRE_INTEGRATION=1` — ошибки с той же причиной

## 2. Окружение CI

- [ ] 2.1 `tools/ci/integration-env.sh` по порядку design.md:
  - `.env` из `.env.example` с разовым токеном, `127.0.0.1` и `AGENT_RUNNER_BIND`;
  - проверка Docker и Compose 2.20+;
  - pull, build, `up -d --wait lbfr-db-test`;
  - строка `/etc/hosts` с IP контейнера в `lbfr-net`;
  - раннер в фоне с журналом и ожиданием ответа на `help`;
  - `::add-mask::` и `$GITHUB_ENV`;
  - коды `0`/`1`/`2`.

  Проверка: `sh -n`; тест скрипта с заглушками `docker`, `sudo`, `python3`/`wget` в `PATH` (по образцу гейта задач выпуска) — содержимое `.env`, строка hosts, переменные в `$GITHUB_ENV`, код `2` без Docker
- [ ] 2.2 `.github/workflows/checks.yml`:
  - шаг «Окружение интеграционных тестов» (`sh tools/ci/integration-env.sh`) перед «Тесты»;
  - последний шаг «Журналы окружения» с `if: failure()` — журнал раннера и `docker compose logs lbfr-db-test`;
  - шапка без оговорки о пропуске, с описанием окружения.

  Проверка: тест сверки из 2.3
- [ ] 2.3 `tests/release/test_checks_workflow.py`:
  - `CI_ONLY` дополнен двумя командами;
  - шаг окружения стоит до «Тесты»;
  - шаг журналов идёт с `if: failure()`;
  - скрипт задаёт `FORGE_REQUIRE_INTEGRATION=1`.

  Прежние проверки зелёные. Проверка: `uv run pytest tests/release` зелёный

## 3. Документация

- [ ] 3.1 `CONTRIBUTING.md`:
  - «Проверки»: вместо «Окружения интеграционных тестов и CLI `backlog` в CI нет…» — что поднимает `checks`, `FORGE_REQUIRE_INTEGRATION`, что в CI пропускаются только тесты CLI `backlog`;
  - «Устройство репозитория»: строка для `tools/ci/`;
  - в «Выпуск версии» убрать оговорку «Проверки в сценарии не исполняют тесты, которым нужно окружение», если она ещё есть;
  - строка версии.

  Проверка: блок команд «Проверки» не изменился — тест сверки зелёный; каркас DGN-008 цел

## 4. Проверки и коммит

- [ ] 4.1 Локальный полный прогон раздела «Проверки» с раннером: интеграционные исполнены и зелёные. Плюс `uv run pytest -m integration` без окружения с `FORGE_REQUIRE_INTEGRATION=1` — падения с причиной. Плюс `openspec validate --specs --strict` и валидация change. Проверка: числа пройденных, пропущенных и упавших тестов в отчёте
- [ ] 4.2 Показать состав коммита и сообщение `LBFR-019: запускать интеграционные тесты в CI` по GIT-016, коммитить после подтверждения. Проверка: рабочее дерево чистое
- [ ] 4.3 По команде владельца — проверка на GitHub: push ветки `release/v0.3.0` и пробный `gh workflow run release.yml --ref release/v0.3.0 -f bump=patch` (job `Проверки` исполняет интеграционные, `release` остановлен гейтом ветки) либо прогон `checks` на PR выпуска. Проверка: в логе шага «Тесты» нет пропусков с причиной про `FORGE_TEST_DB_HOST` или раннер, прогон зелёный; время job'а записано в отчёт

## Workflow follow-up

- Архивировать change в ветке `release/v0.3.0` (`/opsx:archive run-integration-tests-in-ci`) с синком переименования и правки требования в `forge-checks`; отметить задачу 3.5 change `prepare-release-0-3-0`.
- Задача #7 закрывается строкой `Closes #7` в PR выпуска 0.3.0.
