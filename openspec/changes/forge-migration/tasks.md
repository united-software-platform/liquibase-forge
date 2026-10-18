# Tasks

## 1. Загрузка модели в контексте Моделирование

- [x] 1.1 Добавить `LoadModelUseCase` с `LoadModelInput` (путь, признак «нет файла — пустая модель») и `LoadModelOutput` (модель), исключением `InvalidModelError` с нарушениями и повторным использованием `ModelUnreadableError`. Проверка: модульные тесты корректной модели, отсутствующего файла с признаком и без, модели с нарушениями

## 2. Домен Миграции

- [x] 2.1 Реализовать `OperationStamp`: шаблон `YYYYMMDD-HHMMSS`, `logical_file_path` `db/changelog/<штамп>.yaml`, `changeset_id(n)` с номером минимум из двух цифр. Проверка: модульные тесты корректного и некорректных штампов, `id` для 1, 9, 10 и 100
- [x] 2.2 Реализовать изменения `CreateTable` и `AddColumn` (итоговая допустимость NULL у колонки), `NonAdditiveChange` и `NonAdditiveChangeError`, а также `Changelog`: штамп и изменения с назначенными `id`. Проверка: модульные тесты назначения `id` по порядку и неизменяемости
- [x] 2.3 Реализовать доменный сервис `AdditiveDiff`: новые таблицы и колонки в порядке модели попытки; `table_removed`, `column_removed`, `column_type_changed`, `column_nullable_changed` по итоговой допустимости, `primary_key_changed` по упорядоченному ключу; все неаддитивные изменения сразу. Проверка: модульные тесты первой операции (пустая принятая модель), новой колонки, совпадающих моделей, каждого кода, нескольких неаддитивных изменений и явного `nullable: false` у колонки ключа, которое изменением не считается
- [x] 2.4 Реализовать `TargetDatabase` и `TestDatabaseAllowlist` с разбором `хост:порт/имя` и `*` по правилам шлюза. Проверка: модульные тесты совпадения, подстановки `*`, пустого перечня и записи не по формату

## 3. Команда `forge generate`

- [x] 3.1 Объявить контракты `OperationRecordReaderInterface` (штамп, вердикт попытки, каталог попытки), `ChangelogWriterInterface` и `ChangelogReaderInterface` с исключением `OperationRecordUnavailableError`. Реализовать `FrontmatterOperationRecordReader`. Проверка: модульные тесты по беклогу в формате `templates/forge-model.md`: `subject`, `verdict.attempt_N` со значениями `null`, `success`, `failure`; нет файла, нет фронтматтера, штамп не по шаблону
- [x] 3.2 Реализовать `LiquibaseYamlChangelogWriter` и `LiquibaseYamlChangelogReader`: формат из design.md, `logicalFilePath` у каждого changeset, `addPrimaryKey` с `pk_<таблица>` в порядке ключа модели, отображение десяти типов, `databaseChangeLog: []` для пустого changelog; чтение возвращает `id` и объекты changeset. Проверка: модульные тесты текста changelog для таблицы с составным ключом и для колонки, побайтовой повторяемости и обратного чтения записанного файла
- [x] 3.3 Реализовать `GenerateChangelogUseCase`: загрузка обеих моделей, штамп из беклога, разница, запись changelog; при отказе прежний файл `--out` удаляется. Проверка: модульные тесты с подставными контрактами на успех, неаддитивные изменения, некорректную модель попытки (код `1`), повреждённую принятую модель (код `2`), отсутствие беклога
- [x] 3.4 Добавить команду `forge generate --model --accepted --operation --out`: ответ с путём changelog, `logicalFilePath`, перечнем changeset, нарушениями и неаддитивными изменениями; коды `0`, `1`, `2`. Проверка: тесты `tests/cli/test_generate.py` по сценариям требований генерации из `specs/forge-migration/spec.md`, включая побайтовое совпадение двух прогонов
- [x] 3.5 Создать `docs/migration.md` по DOC-014 и DOC-022 с разделами о changelog, идентичности changeset и добавляющих изменениях с кодами; обновить строку `forge generate` в `docs/architecture.md`. Проверка: ссылки относительные, пример changelog из документа совпадает с выводом записи changelog для той же модели (тест)

## 4. Команда `forge apply`

- [x] 4.1 Объявить `LiquibaseGatewayInterface` (`update`, `rollback` с числом), `GatewayResult` и `GatewayUnavailableError`. Реализовать `RunnerLiquibaseGateway`: файл запроса, HTTP-вызов раннера, чтение результата со сверкой `request_id`. Проверка: модульные тесты с подменой HTTP на каждый исход таблицы design.md
- [x] 4.2 Реализовать `EnvironmentSettings` (`FORGE_DB_*`, `FORGE_TEST_DB_ALLOWLIST`, `AGENT_RUNNER_*`) и `ApplyChangelogUseCase`: проверка перечня до раннера, накат, `apply.json` рядом с changelog только при коде шлюза `0` или `1`. Проверка: модульные тесты успеха, ошибки Liquibase, БД вне перечня без вызова шлюза, недоступного шлюза без `apply.json`, не заданных переменных
- [x] 4.3 Добавить команду `forge apply --changelog`. Проверка: тесты `tests/cli/test_apply.py` с подставным шлюзом на коды `0`, `1`, `2`
- [x] 4.4 Интеграционный тест через раннер на `lbfr-db-test`: `generate` модели-примера со всеми десятью типами, `apply`, затем `format_type`, NOT NULL и порядок колонок `pk_<таблица>`; накат пустого changelog. Проверка: тест проходит, а не пропускается
- [x] 4.5 Дополнить `docs/migration.md` разделом о накате и `apply.json`, обновить строку `forge apply` в `docs/architecture.md`. Проверка: описанный состав `apply.json` совпадает с тестом 4.2

## 5. Команда `forge rollback`

- [x] 5.1 Объявить `JournalReaderInterface` (строки журнала по порядку исполнения, отсутствие таблицы журнала), `SchemaProbeInterface` (есть ли таблица или колонка в `public`), `DatabaseRecreatorInterface` и `ResultWriterInterface`; реализовать их на `psycopg` и JSON. Проверка: интеграционные тесты чтения журнала, проверки объектов и пересоздания БД на `lbfr-db-test`
- [x] 5.2 Реализовать `RollbackAttemptUseCase` по диаграмме design.md: вердикт `success`, отсутствие записей, проверка хвоста, откат через шлюз, запасной путь с повторной проверкой перечня, проверка возврата, `rollback.json`. Проверка: модульные тесты с подставными контрактами на каждую ветку диаграммы и на частичный накат (два из трёх changeset)
- [x] 5.3 Добавить команду `forge rollback --operation --attempt`. Проверка: тесты `tests/cli/test_rollback.py` на коды `0`, `1`, `2` и на отсутствие `rollback.json` при вердикте `success`
- [x] 5.4 Интеграционные тесты через раннер на `lbfr-db-test`: накат и откат попытки с подтверждённым возвратом; частичный накат; запасной путь при записи чужого changelog после записей попытки. Проверка: тесты проходят, а не пропускаются
- [x] 5.5 Дополнить `docs/migration.md` разделами об откате, проверке возврата и запасном пути с диаграммой, обновить строку `forge rollback` в `docs/architecture.md`, добавить версию 1.0.2. Проверка: диаграмма укладывается в DOC-018, описанные ветки совпадают с тестами 5.2

## 6. Итоговая проверка

- [x] 6.1 Прогнать `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`, `sh tools/make-lint/check.sh`. Проверка: все проходят, интеграционные тесты выполнены, а не пропущены
- [x] 6.2 Прогнать `openspec validate forge-migration --strict`. Проверка: change валиден

## Workflow follow-up

- Коммит с кодом `LBFR-007` по подтверждению пользователя.
- Архивация change и синхронизация спецификации `forge-migration`, затем слияние ветки `forge-migration` в `feature/first-delivery`.
- Change 4: добавить `--operation {{parent}}` в задачу 2.4 шаблона `templates/forge-apply.md`.
