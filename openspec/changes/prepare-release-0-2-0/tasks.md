# Tasks

## 1. Workflow проверок

- [x] 1.1 Создать `.github/workflows/checks.yml` по design: триггеры `pull_request` и `push` в `main` и `workflow_call`, `permissions: contents: read`, один job на `ubuntu-latest`: `actions/checkout@v4`, `astral-sh/setup-uv@v6` (uv `0.12.7`, Python `3.12`), `uv sync --frozen`, `ruff check`, `ruff format --check`, `mypy src`, `pytest`, `sh tools/make-lint/check.sh`; комментарии в стиле `release.yml`. Проверка: YAML разбирается, шагов с `continue-on-error` нет
- [x] 1.2 Добавить `tests/release/test_checks_workflow.py`: триггеры, права только на чтение, отсутствие `continue-on-error` и `FORGE_TEST_DB_HOST`/`AGENT_RUNNER_*` в `env`, совпадение команд шагов с блоком `bash` раздела «Проверки» `CONTRIBUTING.md` (`pytest tests/<каталог>` покрыт полным `pytest`). Проверка: `uv run pytest tests/release` зелёный; при временно удалённой из workflow команде тест падает

## 2. Релиз через проверки

- [x] 2.1 Переделать `release.yml`: job `checks` вызывает `./.github/workflows/checks.yml` с `contents: read`, job `release` получает `needs: checks` и `contents: write`, верхнеуровневые права — `contents: read`; комментарий шапки о правах и об отсутствии тестов обновить. Проверка: логика шагов `release` и гейт ветки не изменились
- [x] 2.2 Обновить `tests/release/test_release_workflow.py`: права верхнего уровня `contents: read`, `contents: write` только у `release`, `release` зависит от `checks`, `checks` вызывает `checks.yml`, гейт ветки — первый шаг `release`. Проверка: `uv run pytest tests/release` зелёный
- [x] 2.3 `CONTRIBUTING.md`: в «Выпуск версии» убрать «Тестов в сценарии нет», описать прогон `checks` первым job'ом; в «Проверки» — workflow `checks` на PR и push в `main`, какие тесты он пропускает и почему, поведение интеграционных тестов при настроенном, но недоступном раннере (падают с `runner_unavailable`); в «Устройство репозитория» — `checks.yml` и `tests/release/`; новая строка версии `1.0.3` по DOC-022. Проверка: тест из 1.2 зелёный, ссылки относительные

## 3. Документы применяющего

- [x] 3.1 `README.md`: «Шаг 1» — `--ref vX.Y.Z` с пояснением, что тег берётся из Releases; пересказ перечня файлов с блоками заменить указанием на план `--dry-run` (DGN-011); в конце шага — «Подробнее — кейс 7». «Ограничения» — PostgreSQL и схема `public`, только БД из перечня тестовых, смена типа/NULL/PK отклоняется, удаление теряет данные, не больше трёх попыток — каждый пункт со ссылкой на справочник `docs/`. Проверка: каркас DGN-003 сохранён, ссылки и якоря существуют
- [x] 3.2 `docs/use-cases.md`: кейс 7 «Хочу обновить forge до новой версии» (установщик с `--ref`, план с правками владельца и файлами «больше не поставляется», коммит манифеста, перезапуск раннера) и кейс 8 «Хочу разрешить удаления в режиме `auto`» (`/forge … --mode auto --allow-drop`, продолжение остановленной операции с `--allow-drop`, `drop_not_allowed`), метки по DGN-006, голос «я»; навигация, назначение и строка версии `1.0.1`. Проверка: номера 1–6 не сдвинуты, команды совпадают с `install.sh --help` и `docs/operation.md`
- [x] 3.3 `BUSINESS-REQUIREMENTS.md`: пункт границ «только добавляющие изменения» заменить действующими границами (удаление таблиц, колонок и ограничений поддерживается с согласием в `auto`; смена типа, NULL и PK, преобразование данных не поддерживаются) со ссылкой на `docs/migration.md`; строка версии `0.3.0`. Проверка: `grep -n 'добавляющ' BUSINESS-REQUIREMENTS.md` пуст вне таблицы версий
- [x] 3.4 Аудит `project-docs` по `README.md`, `CONTRIBUTING.md`, `docs/use-cases.md`. Проверка: таблица расхождений пуста

## 4. Спеки

- [x] 4.1 Переписать Purpose в `openspec/specs/forge-delivery/spec.md` (вместо `TBD`) и `openspec/specs/forge-migration/spec.md` (разница моделей с добавлениями и удалениями вместо «добавляющей разницы»). Проверка: `openspec validate --specs --strict` проходит
- [x] 4.2 Проверить дельты change. Проверка: `openspec validate prepare-release-0-2-0 --strict` проходит

## 5. Итоговые проверки

- [x] 5.1 Все команды раздела «Проверки» `CONTRIBUTING.md` зелёные в контейнере агента
- [x] 5.2 Полный `uv run pytest` при запущенном на хосте раннере: 0 упавших (критерий задачи #6)

## Workflow follow-up

- Архивировать change в ветке `release/v0.2.0` до PR, чтобы спеки попали в `main` вместе с кодом.
- Показать состав коммита и сообщение `LBFR-018: подготовить выпуск 0.2.0` (GIT-016), коммит и push — по подтверждению.
- PR `release/v0.2.0` → `main` с `Closes #5`, `Closes #6`; слияние после зелёного `checks`.
- `gh workflow run release.yml --ref main -f bump=minor` — по команде владельца.
- Проверить `releases/latest`, бейдж версии, установщик без `--ref` с `--dry-run`; текст релиза — `gh release edit v0.2.0`.
