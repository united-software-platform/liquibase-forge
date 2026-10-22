# Tasks

## 1. Diff моделей с удалениями

- [x] 1.1 Переименовать `AdditiveDiff` в `ModelDiff`, `NonAdditiveChange`/`NonAdditiveChangeError` — в `UnsupportedChange`/`UnsupportedChangeError`, обновить импорты и тесты; проверка — `uv run pytest tests/migration` зелёный без изменения поведения
- [x] 1.2 Добавить `DropTable` и `DropColumn` в `SchemaChange`; `ModelDiff.between` выдаёт их вместо отказов `table_removed`/`column_removed`, удаление колонки PK даёт только `primary_key_changed`; порядок — удалённые таблицы, удалённые колонки, добавления; проверка — тесты `test_additive_diff.py` (переименовать в `test_model_diff.py`) на удаление таблицы, колонки, колонки PK, переименование и порядок

## 2. Changelog и `forge generate`

- [x] 2.1 Рендерить `dropTable` с `rollback: [createTable, addPrimaryKey]` и `dropColumn` с `rollback: [addColumn]` по принятому определению; проверка — тест `test_liquibase_changelog.py` на точный YAML и побайтовую повторяемость
- [x] 2.2 Ответ `forge generate`: виды changeset `drop_table`/`drop_column`, коды удалений ушли из `non_additive`; проверка — `tests/migration/application/test_generate_changelog.py` и `tests/cli/test_generate.py`
- [x] 2.3 Обновить `docs/migration.md` (changelog с примером удаления, порядок, таблица отказов, откат) и `tests/migration/test_migration_doc.py`, сверяющий пример с выводом `forge generate`; проверка — тест документа зелёный
- [x] 2.4 Обновить `docs/model-format.md` и `docs/domain.md` (ограничение «только добавляющие изменения» → допустимы добавление и удаление); проверка — `tests/modeling/test_model_format_doc.py` зелёный, в документах нет утверждения об отклонении удаления

## 3. Согласие на удаления

- [x] 3.1 `OperationRecord` и `OperationRecordReader` читают `mode` и `allow_drop` (нет поля — `False`); проверка — тесты `test_operation_record_reader.py` для беклога с полем и без
- [x] 3.2 `GenerateChangelogUseCase` бросает `DropNotAllowedError` в `auto` без `allow_drop` при наличии удалений и удаляет прежний `--out`; команда отвечает кодом `2`, вид `drop_not_allowed`, перечень объектов; проверка — модульные и CLI-тесты на сценарии `auto` без согласия, с согласием, прежний шаблон, `interactive`
- [x] 3.3 Шаблон `forge-model` 1.2.0: флаг `allow-drop`, поле `allow_drop`, передача `--flag allow-drop`/`--no-flag allow-drop` в задачи порождения попыток; проверка — `tests/operation/test_templates.py` и `backlog check-template`
- [x] 3.4 Шаблон `forge-apply` 1.3.0: поле `allow_drop`; стоп-знак 3.1 показывает перечень удалений с предупреждением; условие гейта 3.1 без «только добавляющие изменения»; проверка — `tests/operation/test_templates.py` и `backlog check-template`
- [x] 3.5 Навык `.claude/skills/forge/SKILL.md`: ключ `--allow-drop` только с `--mode auto`, передача флага в `backlog generate`, сообщение о непринятом ключе при открытой операции, строка версионирования; проверка — чтение по сценариям спецификации `forge-operation`
- [x] 3.6 Обновить `docs/operation.md` и `docs/architecture.md` (режим, `allow_drop`, `drop_not_allowed` в контракте `forge generate`, ограничения); проверка — описание совпадает с дельтами спецификаций

## 4. Откат удалений

- [x] 4.1 `ChangelogSummary` получает `dropped_tables` и `dropped_columns`, читатель распознаёт `dropTable`/`dropColumn`; проверка — тесты `test_liquibase_changelog.py` на сводку
- [x] 4.2 `RollbackAttemptUseCase` добавляет проверки `table_present` и `column_present`; проверка — `tests/migration/application/test_rollback_attempt.py` на пройденную и непройденную проверку
- [x] 4.3 Дополнить раздел «Проверка возврата» `docs/migration.md` проверками `table_present` и `column_present`; проверка — тест документа зелёный

## 5. `allow_drop` и `destructive` в статусе и отчёте

- [x] 5.1 `Operation`, `frontmatter.py` и `views.py`: поле `allow_drop` (умолчание `False`) в ответах `forge status` и `forge report`; проверка — `tests/operation/infrastructure/test_frontmatter.py`, `tests/cli/test_status.py`, включая фикстуру `forge-model-1.0.0.md` без поля
- [x] 5.2 `AttemptResultsReaderInterface.destructive` и реализация в `attempt_results.py`; `BuildReportUseCase` выдаёт `destructive` для итогового changelog; проверка — `test_attempt_results.py`, `test_build_report.py`, `tests/cli/test_report.py` (успех с удалениями, без удалений, без попыток) и тест, сверяющий читатель с выводом рендера
- [x] 5.3 Описать `allow_drop` и `destructive` в `docs/operation.md`; проверка — описание совпадает с дельтой `forge-operation-commands`

## 6. Интеграционная проверка

- [x] 6.1 Интеграционный тест на `lbfr-db-test`: удаление колонки и удаление таблицы проходят накат, сверку без расхождений, откат Liquibase с пройденными `column_present`/`table_present`; проверка — `uv run pytest -m integration` зелёный
- [x] 6.2 Интеграционный тест частичного наката changelog «удаление + создание»: откат снимает ровно записанные changeset, удалённое восстановлено; проверка — `uv run pytest -m integration` зелёный
- [x] 6.3 Прогнать проверки репозитория: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`; проверка — все команды завершаются кодом `0`

## 7. Согласие при продолжении

- [x] 7.1 Доменная операция `Operation.grant_drop()`: только в статусе `stopped` и режиме `auto`, `allow_drop` меняется с `false` на `true`, повтор ничего не меняет, иначе — ошибка перехода; проверка — `tests/operation/domain/test_operation.py`
- [x] 7.2 `FrontmatterOperationWriteRepository` пишет строку `allow_drop` в беклог операции и в беклоги попыток из `backlog.attempt_N`: замена строки либо вставка после `mode`, остальной текст побайтово прежний; проверка — `tests/operation/infrastructure/test_frontmatter.py`, включая фикстуру `forge-model-1.0.0.md` без поля
- [x] 7.3 `forge resume --operation <беклог> --allow-drop`: сценарий смены статуса и команда; коды `0`/`1`/`2` по дельте `forge-operation-commands`; проверка — `tests/cli/test_stop_resume.py` на согласие, беклог прежнего шаблона, повтор, `interactive` и `running`
- [x] 7.4 Шаблон `forge-model` 1.2.0: задачи порождения попыток 2.1, 3.1, 4.1 выбирают `--flag allow-drop` или `--no-flag allow-drop` по `allow_drop` фронтматтера беклога операции вместо флага, вшитого при порождении; проверка — `tests/operation/test_templates.py` и `backlog check-template`
- [x] 7.5 Навык `.claude/skills/forge/SKILL.md`: остановленная операция `auto` с ключом — `forge resume --allow-drop`; операция `running` — ключ не принят; операция `interactive` — ключ не нужен, операция продолжается; строка версионирования; проверка — чтение по сценариям дельты `forge-operation`
- [x] 7.6 Сообщение отказа `drop_not_allowed` называет продолжение `/forge --mode auto --allow-drop`; проверка — `tests/cli/test_generate.py`
- [x] 7.7 Обновить `docs/operation.md` (согласие при продолжении вместо неизменности признака, `forge resume --allow-drop` в таблице команд, шаблон `forge-model` 1.2.0) и `docs/architecture.md` (контракт `forge resume`); проверка — описание совпадает с дельтами спецификаций
- [x] 7.8 Прогнать проверки репозитория: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`; проверка — все команды завершаются кодом `0`

## Workflow follow-up

- Синхронизировать дельты в основные спецификации и архивировать изменение `/opsx:archive` после ревью.
- Закрыть задачу GitHub #3 (LBFR-014) после слияния.
