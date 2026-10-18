# Tasks

## 1. Общее ядро и описание типа

- [x] 1.1 Перенести в `src/forge/shared/` (домен, приложение, инфраструктура) `TargetDatabase`, `AllowedDatabase`, `TestDatabaseAllowlist`, `parse_allowlist`, `DatabaseNotAllowedError`, `InvalidAllowlistError`, `DatabaseCredentials`, `TargetDatabaseSettingsInterface`, `SettingsUnavailableError`, `DatabaseUnavailableError`, `ResultWriterInterface`, `EnvironmentSettings` без настроек раннера, `PostgresConnector`, `JsonResultWriter`. Настройки раннера оставить функцией `runner_settings(env)` в `migration/infrastructure`; перевести `migration`, `cli` и тесты на новые импорты, тесты перенесённых компонентов перенести в `tests/shared/`. Проверка: `grep` не находит старых путей импорта, `uv run pytest` и `uv run mypy src` проходят без правки утверждений тестов
- [x] 1.2 Добавить `ColumnType.__str__` (`string(255)`, `decimal(12, 2)`, `uuid`) и заменить им `_type` в `migration/domain/additive_diff.py`. Проверка: модульный тест описания всех десяти типов, тесты неаддитивных изменений проходят

## 2. Домен Сверки

- [x] 2.1 Реализовать `ActualColumn`, `ActualTable`, `ActualSchema` и `Discrepancy`. Проверка: модульные тесты неизменяемости и доступа к таблице и колонке по имени
- [x] 2.2 Реализовать доменный сервис `SchemaComparison`: `table_missing`, `table_unexpected`, `column_missing`, `column_unexpected`, `column_type_mismatch` (включая тип вне формата), `column_nullable_mismatch` по итоговой допустимости, `primary_key_mismatch` (порядок, отсутствие ключа), без сравнения порядка колонок и имени ключа; порядок расхождений по design.md. Проверка: модульные тесты на каждый вид, на совпадающую схему, на отсутствующую таблицу без расхождений колонок и на устойчивый порядок
- [x] 2.3 Реализовать `ExpectedChangeSet`, `JournalRecord` и `JournalCheck`: запись с теми же `id`, `author`, `filename` и `EXECTYPE = EXECUTED`. Проверка: модульные тесты на исполненный, отсутствующий, `MARK_RAN` changeset, на чужой `filename` и на пустой changelog

## 3. Интроспекция, журнал и changelog

- [x] 3.1 Объявить контракты `SchemaIntrospectorInterface`, `JournalRecordsReaderInterface`, `ChangesetListReaderInterface` с `ChangelogUnreadableError`; реализовать `YamlChangesetListReader`. Проверка: модульные тесты на changelog `forge generate`, пустой changelog, нечитаемый и чужой файл
- [x] 3.2 Реализовать `PsycopgSchemaIntrospector` с обратным отображением типов по таблице design.md и `PsycopgJournalRecordsReader`. Проверка: интеграционные тесты на `lbfr-db-test` — все десять типов, тип вне формата (`smallint`, `varchar` без длины), NOT NULL, составной ключ в порядке, таблица без ключа, исключение таблиц журнала, журнал без таблицы и с записями

## 4. Команда `forge reconcile`

- [x] 4.1 Реализовать `ReconcileUseCase`: проверка перечня тестовых до подключения, загрузка модели, интроспекция, журнал, сравнение, `reconcile.json` рядом с changelog только при вердикте. Проверка: модульные тесты с подставными контрактами на `success`, `failure`, БД вне перечня без подключения, недоступную БД, некорректную модель и нечитаемый changelog без `reconcile.json`
- [x] 4.2 Добавить команду `forge reconcile --model --changelog`: ответ с вердиктом и расхождениями, коды `0`, `1`, `2`. Проверка: тесты `tests/cli/test_reconcile.py` на каждый код и на побайтово одинаковый вывод двух прогонов
- [x] 4.3 Интеграционный тест через раннер на `lbfr-db-test`: `generate` и `apply` модели-примера со всеми десятью типами, затем `reconcile` без расхождений; затем правки БД (лишняя колонка, другая длина строки, снятый NOT NULL, удалённая запись журнала, `MARK_RAN`) дают соответствующие расхождения с кодом `1`. Проверка: тест проходит, а не пропускается

## 5. Документация

- [x] 5.1 Создать `docs/reconciliation.md` по DOC-014 и DOC-022: что сравнивается и что нет, обратное отображение типов, виды расхождений с примером `reconcile.json`, порядок, коды; обновить строку `forge reconcile` в `docs/architecture.md` и добавить версию 1.0.3. Проверка: пример `reconcile.json` из документа совпадает по составу полей с выводом команды (тест), ссылки относительные

## 6. Итоговая проверка

- [x] 6.1 Прогнать `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`, `sh tools/make-lint/check.sh`. Проверка: все проходят, интеграционные тесты выполнены, а не пропущены
- [x] 6.2 Прогнать `openspec validate forge-reconciliation --strict`. Проверка: change валиден

## Workflow follow-up

- Коммит с кодом `LBFR-008` по подтверждению пользователя.
- Архивация change и синхронизация спецификации `forge-reconciliation`, затем слияние ветки `forge-reconciliation` в `feature/first-delivery`.
