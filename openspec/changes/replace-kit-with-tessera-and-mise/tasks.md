# Tasks

## 1. Окружение на mise

- [x] 1.1 Завести `mise.toml`: закрепить в `[tools]` интерпретатор Python 3.12 и `uv`, в `[env]` — несекретные координаты forge, `_.file = ".env"` и перечень тестовых БД с шаблоном `t_*`, объявить задачи `forge`, `forge-env-up`, `forge-env-check`, `lint`, `format-check`, `types`, `test`; проверить: `mise tasks` перечисляет семь задач вместе с задачами общего набора (`env-up`, `env-status`), а `mise run lint`, `mise run format-check`, `mise run types` проходят на текущем коде
- [x] 1.2 Выяснить мажорную версию Java, которой требует Liquibase `5.0.4` из плагина mise, закрепить Java и Liquibase в `[tools]`; проверить: `mise install` завершается без Docker, а `mise x -- liquibase --version` печатает `5.0.4`
- [x] 1.3 Удалить `Makefile`, `docker-compose.yml`, `docker/`, `tools/host-runner/`, `tools/make-lint/` и `.sdd-kit-manifest.json`, убрать исключение `tools/host-runner` из `pyproject.toml`; проверить: `git ls-files Makefile docker-compose.yml docker tools/host-runner tools/make-lint .sdd-kit-manifest.json` пуст, а `mise run lint` проходит
- [x] 1.4 Переписать `.env.example` под шаблон секретов — имена `FORGE_DB_PASSWORD`, `FORGE_DB_ADMIN_PASSWORD`, `FORGE_TEST_DB_USER`, `FORGE_TEST_DB_PASSWORD` с пустыми значениями — и `.gitignore` без блока kit'а и записи `/data/lbfr-db/`; проверить: `git check-ignore .env` выводит `.env`, в `.env.example` нет переменных `AGENT_RUNNER_*`, `SDD_KIT_*` и `LBFR_*`
- [x] 1.5 Переписать в `docs/use-cases.md` кейсы окружения: 1 (подключение клиентом к общему экземпляру), 2 (подготовка окружения с нуля), 6 (смена версии Liquibase в `mise.toml` и драйвера парой переменных), 14 (два проекта на одном экземпляре workspace), 17 (перенос данных целевой БД на общий экземпляр); проверить: в кейсах 1, 2, 6 и 14 нет команд `make` и переменных прежнего окружения, в кейсе 17 команды Docker относятся только к выгрузке данных из прежнего контейнера, а ссылки на кейсы 2 и 14 в `README.md` ведут на новые заголовки

## 2. Шлюз Liquibase в процессе CLI

- [x] 2.1 Добавить в разбор перечня тестовых БД шаблон префикса (`t_*`) и отказ для `*` не в конце имени в `src/forge/shared/domain/target_database.py`; проверить: тесты в `tests/shared/domain/test_target_database.py` покрывают префикс, соседнюю базу вне префикса и некорректную запись и проходят
- [x] 2.2 Задать в `EnvironmentSettings` значения по умолчанию: хост `localhost`, порт `PG_PORT`, иначе `5432`, для целевой БД и сервера тестов; проверить: тесты в `tests/shared/infrastructure/test_settings.py` покрывают оба варианта порта и отсутствие `FORGE_DB_NAME` и проходят
- [x] 2.3 Заменить `RunnerLiquibaseGateway` реализацией шлюза в процессе: проверки пути changelog и перечня, запуск `liquibase` из `PATH` с search path корня проекта, classpath драйвера из `.forge/lib/` и рабочим каталогом вне проекта, учётные данные окружением, коды `0`/`1`/`2` и ошибка `liquibase_unavailable`; удалить `src/forge/shared/infrastructure/runner.py`, `runner_gateway.py` и `tools/liquibase/`, подключить шлюз в командах `apply` и `rollback`, переписать `tests/tools/test_liquibase_gateway.py` в тесты новой реализации; проверить: модульные тесты шлюза (состав команды, пароль вне аргументов, отказы без запуска) и `mise run test -- tests/migration tests/cli` проходят, файлы `.forge/liquibase-request.json` и `.forge/liquibase-result.json` не создаются
- [x] 2.4 Заменить в `EnvironmentProbe` проверку `runner` проверкой `liquibase` — запуск `liquibase --version` с пределом времени и наличие файла драйвера; проверить: тесты в `tests/operation/infrastructure/test_environment_probe.py` и `tests/cli` проходят, ответ `forge status` называет проверки `database`, `allowlist`, `liquibase`, `accepted`
- [x] 2.5 Переписать фикстуры интеграционных тестов: убрать `runner_configured` и переменные `AGENT_RUNNER_*`, пропускать тест без `FORGE_TEST_DB_HOST` или без Liquibase, переписать сквозной тест шлюза на нативный Liquibase с накатом `master.yaml` с записями `include` и сравнением дерева проекта до и после; проверить: `FORGE_REQUIRE_INTEGRATION=1 mise run test -- tests/integration` проходит на демоне `postgres` workspace
- [x] 2.6 Обновить `docs/migration.md` (код `liquibase_unavailable`, без кодов раннера и файла результата), `docs/operation.md` (проверка `liquibase`, запуск `forge` вместо обёртки), раздел «Окружение исполнения» `docs/architecture.md` и кейсы 5 и 11 `docs/use-cases.md`; проверить: `grep -nE "раннер|runner|forge\.sh|docker" docs/migration.md docs/operation.md docs/architecture.md` находит только исторические строки таблиц версий, а тесты документов проходят

## 3. Команды среды

- [x] 3.1 Реализовать хранилище драйвера: загрузка в `.forge/lib/` с проверкой контрольной суммы, замена файла с неверной суммой, пара переменных версии и суммы, файл `.forge/.gitignore` со строкой `*`; проверить: модульные тесты с подставным транспортом покрывают загрузку, повреждённый файл, версию без суммы и неудачную загрузку и проходят
- [x] 3.2 Реализовать подготовку целевой БД: соединение администратора (`FORGE_DB_ADMIN_*`, иначе учётные данные целевой БД), создание роли и базы при отсутствии, существующие не меняются; проверить: модульные тесты с подставным подключением проверяют порядок SQL и отказ без прав и проходят
- [x] 3.3 Добавить команды `forge env up` и `forge env check`: вывод JSON с массивом `checks` (`name`, `ok`, `message`), коды `0` и `2`, неизменность следа операций; проверить: модульные тесты команд в `tests/cli` проходят, а `mise run test -- tests/cli` зелёный
- [x] 3.4 Добавить интеграционные тесты команд среды на демоне `postgres` workspace: создание и повторный запуск, проверка среды, очистка тестовых объектов; проверить: `FORGE_REQUIRE_INTEGRATION=1 mise run test -- tests/integration -k env` проходит
- [x] 3.5 Довести задачи mise и справочник команд: `mise run forge-env-up` и `mise run forge-env-check` завершаются кодом `0` на подготовленном рабочем месте, `docs/operation.md` описывает команды среды с таблицей кодов возврата; проверить: обе задачи отработали на локальном рабочем месте, а команды из справочника запускаются как записаны

## 4. Правила из плагина tessera

- [x] 4.1 Удалить `rules/`, `CLAUDE.md` и переписать `AGENTS.md` в точку входа: источник правил — плагин tessera и его навык-каталог, путь харнеса без плагинов, перечень проектных документов; добавить строку версий с подтверждённым владельцем номером задачи (GIT-010); проверить: `git ls-files rules CLAUDE.md` пуст, а `AGENTS.md` называет плагин tessera и `CONTRIBUTING.md`
- [x] 4.2 Убрать из `CONTRIBUTING.md` раздел «Отличия от поставки kit'а» и заменить ссылки на `./rules/` кодами правил tessera (`GIT-009`, `GIT-012`, `GIT-015`, `GIT-021`, `DOC-014`, `DGN-001`, `CLAR-001`, `ENV-006`), убрать коды `DOCK-*` и `TERM-*` из `docs/domain.md` и `docs/use-cases.md`; проверить: `grep -rnE "\]\(\./rules/|\b(MAKE|DOCK|TERM)-[0-9]{3}" --include=*.md .` без каталога `openspec/changes/` не находит ни одной строки вне строк таблиц версий

## 5. Плагин forge

- [x] 5.1 Перенести навык в `plugins/forge-plugin/skills/forge/SKILL.md`, а шаблоны операций — в `plugins/forge-plugin/skills/forge/templates/`; в навыке заменить обёртку командой `forge`, добавить шаг переноса шаблонов в `templates/` проекта и отказ без CLI, заменить ссылки на документы репозитория их называнием, дополнить поиск CLI `backlog` каталогом кеша ZCode; добавить строку версий; проверить: `grep -rn "forge\.sh\|tools/forge-env" plugins` пуст, в каталоге навыка четыре шаблона
- [x] 5.2 Создать зеркальные манифесты `plugins/forge-plugin/.zcode-plugin/plugin.json` и `.claude-plugin/plugin.json`, каталог маркетплейса `.claude-plugin/marketplace.json` с записями `forge-plugin` и `backlog`, `plugins/forge-plugin/README.md`; написать тесты плагина (манифесты — корректный JSON и совпадают, записи маркетплейса на месте, в плагине нет `tests/`, `docs/`, `openspec/`); проверить: `mise run test -- tests/plugin` проходит
- [x] 5.3 Удалить `install.sh`, `delivery.txt`, `install/`, `tools/forge-env/` и тесты установщика (`tests/delivery/`, `tests/tools/test_forge_env.py`), убрать их исключения из `pyproject.toml`; проверить: `git ls-files install.sh delivery.txt install tools/forge-env tests/delivery` пуст, `mise run lint` и `mise run test` проходят
- [x] 5.4 Убрать `.claude/` из индекса командой `git rm -r --cached .claude`, добавить `.claude/` и `.zcode/` в `.gitignore`, не трогая файлы на диске; проверить: `git ls-files .claude .zcode` пуст, а `ls .claude/skills` на рабочем месте по-прежнему перечисляет навыки
- [x] 5.5 Переписать `README.md` под плагин: установка плагина из маркетплейса и CLI из релизного тега, подготовка среды командами mise и `forge env`, вызов `/forge`; обновить в `CONTRIBUTING.md` разделы «Устройство репозитория» и «Локальная настройка» (перечень задач не повторять), кейсы 7 и 12 `docs/use-cases.md`; проверить: `grep -nE "install\.sh|make |docker|раннер|kit" README.md CONTRIBUTING.md docs/use-cases.md` находит только исторические строки, аудит навыком `project-docs` не находит расхождений

## 6. Проверки и CI

- [x] 6.1 Переписать `tools/ci/integration-env.sh`: запуск предустановленного сервера PostgreSQL образа раннера, координаты тестов и `FORGE_REQUIRE_INTEGRATION=1` в `$GITHUB_ENV`, драйвер через `forge env up`; переписать `tests/release/test_integration_env.py`; проверить: тесты проходят, а `grep -nE "docker|runner" tools/ci/integration-env.sh` пуст
- [x] 6.2 Переписать `.github/workflows/checks.yml`: инструменты через mise с точной версией действия, `uv sync --frozen`, задачи `lint`, `format-check`, `types`, `test`, job с именем «Линтер, форматирование, типы, тесты», журнал PostgreSQL при сбое; обновить `tests/release/test_checks_workflow.py`; проверить: `mise run test -- tests/release/test_checks_workflow.py` проходит, в файле workflow нет вызовов `docker`
- [x] 6.3 Заменить в `.github/rulesets/main.json` имя обязательной проверки на новое имя job'а; проверить: `mise run test -- tests/release/test_main_ruleset.py` проходит
- [x] 6.4 Привести раздел «Проверки» `CONTRIBUTING.md` к задачам mise и убрать из него шаг объёма секций `Makefile`; проверить: тест соответствия workflow и раздела проходит
- [x] 6.5 Прогнать полный набор локально: `mise install`, `mise run env-up`, `mise run forge-env-up`, затем `FORGE_REQUIRE_INTEGRATION=1 mise run test`, `mise run lint`, `mise run format-check`, `mise run types`; проверить: все семь команд завершаются кодом `0` без Docker

## 7. Релиз

- [x] 7.1 Добавить в `.github/workflows/release.yml` гейт версии плагина после разбора версии и до гейта задач: сверка поля `version` обоих манифестов и записи маркетплейса с выпускаемым номером, отказ до любой записи; обновить `tests/release/test_release_workflow.py`; проверить: тесты гейта (расхождение, совпадение, место перед записью) проходят
- [x] 7.2 Описать в `CONTRIBUTING.md` в разделе «Выпуск версии» гейт версии плагина и порядок подготовки: номер в манифесты вносит разработчик в изменении `prepare-release-X.Y.Z`; проверить: раздел называет гейт, а `test_release_commit_changes_only_version` по-прежнему проходит
- [x] 7.3 Обновить назначение `## Purpose` спецификаций `forge-delivery`, `forge-environment`, `forge-liquibase-gateway` и `forge-checks` в `openspec/specs/`; проверить: `openspec validate --all --strict` проходит, а в назначениях нет упоминаний kit'а, Compose и раннера

## 8. Итоговая проверка

- [x] 8.1 Пройти основной путь `README.md` в чистом временном каталоге: установить CLI из локального дерева, объявить инструменты и координаты в `mise.toml` проекта, выполнить `forge env up` и `forge env check`; проверить: `forge env check` возвращает код `0` против демона `postgres` workspace, файлы проекта не изменились
- [x] 8.3 Пройти полный цикл операции в чистом проекте через установленный CLI — модель, changelog, накат, сверка, закрытие, отчёт, принятие в корень принятого состояния проекта; проверить: вручную — беклоги операции и попытки порождены реальным CLI `backlog` по шаблонам плагина командами из текста беклога, автоматически — `FORGE_REQUIRE_INTEGRATION=1 mise run test -- tests/integration/test_clean_project.py`
- [x] 8.2 Проверить чистоту репозитория: `openspec validate --all --strict` проходит, `git ls-files` не содержит путей kit'а, Docker, `Makefile` и установщика, `grep -rnE "AGENT_RUNNER|docker compose|forge\.sh|sdd-developer-kit" --include=*.md --include=*.py --include=*.sh --include=*.yml --include=*.toml .` без `openspec/changes/` находит только исторические строки таблиц версий

## Workflow follow-up

- Владелец устанавливает плагин tessera в харнес до работы в репозитории после слияния.
- До слияния PR владелец применяет ruleset с новым именем проверки: `sh tools/github/apply-ruleset.sh .github/rulesets/main.json`.
- После слияния владелец пересоздаёт на рабочих местах ссылку `.zcode/skills/forge` на каталог навыка плагина и удаляет локальную копию навыка `project-docs` kit'а.
- Архивировать изменение после проверки владельцем командой `/openspec-archive-change`.
