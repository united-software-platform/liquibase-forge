# Proposal

## Why

SDD Developer Kit уходит из разработки Liquibase Forge: он привязан к песочнице — контейнеру
агента, раннеру целей `make` и Docker Compose, — а стандартом окружения workspace стал mise.
Пока forge собран на kit'е, его нельзя ни разрабатывать по новому стандарту, ни поставить
в проект без kit'а: установщик патчит файлы kit'а, CLI доходит до Liquibase только через раннер,
а проверки поднимают Compose. На смену kit'а приходит плагин tessera — та же методология правил
и навыков без привязки к харнесу и песочнице.

## What Changes

- **BREAKING**: файлы поставки kit'а удаляются из репозитория — `.sdd-kit-manifest.json`,
  `rules/`, `CLAUDE.md`, `Makefile`, `docker-compose.yml`, `tools/host-runner/`,
  `tools/make-lint/`, навык `project-docs`. Правила процесса приходят из плагина tessera;
  `AGENTS.md` остаётся единственной точкой входа к ним.
- Каталоги харнесов `.claude/` и `.zcode/` становятся локальной регистрацией вне индекса git:
  навыки OpenSpec разворачивает `openspec init`, каталог `openspec/` остаётся в репозитории.
- **BREAKING**: Docker и Docker Compose не используются. `docker-compose.yml` и `docker/`
  удаляются вместе с сервисами `lbfr-db`, `lbfr-db-test` и образом `lbfr-liquibase`.
- **BREAKING**: `Makefile` заменяется `mise.toml` — единый менеджер инструментов, переменных
  и задач. Цели `forge-env-*` и проверки становятся задачами mise; цели `liquibase-update`
  и `liquibase-rollback` исчезают вместе с раннером.
- PostgreSQL forge берётся из общего набора workspace через каскад mise: целевая БД операций
  и тестовые БД — отдельные базы на общем экземпляре, изоляция в перечне тестовых БД усиливается
  шаблоном префикса `t_*`.
- Liquibase исполняется нативно как инструмент mise; драйвер PostgreSQL загружается в
  `.forge/lib/` с проверкой контрольной суммы вместо сборки образа.
- **BREAKING**: раннер, его белый список и файлы обмена `.forge/liquibase-request.json` и
  `.forge/liquibase-result.json` удаляются. CLI вызывает шлюз Liquibase в своём процессе;
  проверка среды `runner` сменяется проверкой `liquibase`.
- Добавляются команды `forge env check` и `forge env up`: проверка среды и идемпотентная
  подготовка — создание целевой БД, загрузка драйвера.
- **BREAKING**: поставка в целевые проекты — плагин по образцу tessera вместо `install.sh`:
  зеркальные манифесты, маркетплейс, навык `forge` с шаблонами операций; CLI ставится
  uv-инструментом из релизного тега. `install.sh`, `delivery.txt`, `install/blocks/` и
  `.forge-manifest.json` удаляются.
- Проверки в GitHub Actions идут без Docker: инструменты ставит mise, сервер PostgreSQL —
  нативный образа раннера. Job проверок переименован, ruleset `main` обновляется той же правкой.
- Релизный сценарий получает гейт версии плагина: манифесты и запись маркетплейса должны
  повторять выпускаемый номер.
- Документы приводятся к новому состоянию: `README.md`, `CONTRIBUTING.md`, `AGENTS.md`,
  `docs/architecture.md`, `docs/migration.md`, `docs/operation.md`, `docs/use-cases.md`
  (кейсы 1, 2, 5, 6, 7, 11, 12, 14, 17) и навык `forge`.

## Capabilities

### New Capabilities

- `forge-environment-commands`: команды `forge env check` и `forge env up` — состав проверок
  среды, коды возврата и идемпотентная подготовка целевой БД и драйвера Liquibase.
- `forge-development-process`: источник правил и навыков процесса в репозитории forge — плагин
  tessera, точка входа `AGENTS.md`, локальная регистрация харнесов и OpenSpec как процесс
  разработки.

### Modified Capabilities

- `sdd-kit-delivery`: вся способность удаляется — kit больше не поставляется в проект.
- `forge-delivery`: установка установщиком с блоками в файлах kit'а заменяется плагином
  (манифесты, маркетплейс, навык с шаблонами) и установкой CLI из релизного тега.
- `forge-environment`: Docker Compose, публикация портов, имена контейнеров и каталог данных
  заменяются окружением на mise — инструменты, задачи, переменные и PostgreSQL общего набора
  workspace.
- `forge-liquibase-gateway`: обмен файлами через раннер заменяется вызовом шлюза из процесса CLI,
  контейнер `lbfr-liquibase` — нативным Liquibase с драйвером из `.forge/lib/`; перечень
  тестовых БД получает шаблон префикса.
- `forge-migration`: накат и откат идут через шлюз без раннера; ошибкой окружения становится
  недоступный Liquibase, а не раннер.
- `forge-operation-commands`: `forge status` проверяет Liquibase вместо раннера; сценарии
  ошибок окружения названы по Liquibase.
- `forge-operation`: правило кода `2` ограничивается командами операции — команды среды его
  не вызывают; сценарий ошибки окружения при накате назван по Liquibase вместо раннера.
- `forge-checks`: проверки повторяют задачи mise, объём секций `Makefile` не проверяется,
  окружение интеграционных тестов в CI — нативный PostgreSQL и Liquibase без Docker и раннера.
- `forge-release`: номер версии в манифестах плагина вносит разработчик, релизный сценарий
  сверяет его с выпускаемой версией; установка идёт из релизного тега, а не установщиком.

## Impact

- **Код CLI**: `src/forge/shared/infrastructure/runner.py`,
  `src/forge/migration/infrastructure/runner_gateway.py`,
  `src/forge/operation/infrastructure/environment_probe.py`, команды `apply`, `rollback`,
  `status` — переход с раннера на шлюз в процессе; добавляются команды `forge env`; разбор
  перечня тестовых БД — в `src/forge/shared/domain/target_database.py`.
- **Удаляемые инструменты**: `tools/host-runner/`, `tools/make-lint/`, `tools/forge-env/`,
  `tools/liquibase/gateway.py`, `tools/ci/integration-env.sh`, `docker/`, `install.sh`,
  `install/`, `delivery.txt`.
- **Тесты**: `tests/delivery/` переписывается под плаг; `tests/tools/` — под шлюз в процессе
  CLI; `tests/release/test_integration_env.py`, `test_checks_workflow.py`,
  `test_release_workflow.py` — под mise и нативный PostgreSQL; фикстуры раннера в
  `tests/integration/`, `tests/migration/`, `tests/shared/`, `tests/operation/` заменяются
  фикстурой доступного Liquibase.
- **Внешние системы**: рабочее место разработчика требует запущенного демона `postgres`
  workspace (`mise run env-up`) и установленного в харнесе плагина tessera.
- **Действия владельца при внедрении**: установить плагин tessera в харнес; применить
  ruleset `main` с новым именем проверки до слияния PR изменения.
- **Целевые проекты**: проекты с поставленным установщиком forge migrируют вручную —
  порядок описан в кейсе 12 документа кейсов.
