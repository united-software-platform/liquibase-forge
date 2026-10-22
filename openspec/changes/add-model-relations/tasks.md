# Tasks

## 1. Формат модели и проверка

- [ ] 1.1 Черновик и чтение YAML: поля `foreign_keys` (`columns`, `references.table`, `references.columns`) и `unique`, структурные нарушения `missing_field`, `unknown_field`, `wrong_kind` для новых полей; проверка — тесты `test_yaml_reader.py`, включая `on_delete` → `unknown_field`
- [ ] 1.2 Объекты-значения `UniqueSet` и `ForeignKey` с тождеством по содержимому; `Table` получает `unique` и `foreign_keys`; проверка — тесты домена на равенство при перестановке
- [ ] 1.3 Правила `unique` в фабрике: `empty_unique`, `unique_unknown_column`, `unique_duplicate_column`, `unique_equals_primary_key`, `unique_duplicate`; проверка — `test_factory.py` и `test_validate_model.py` по сценариям дельты `forge-data-model`
- [ ] 1.4 Второй проход фабрики для FK: `empty_foreign_key`, `foreign_key_unknown_column`, `foreign_key_duplicate_column`, `foreign_key_unknown_table`, `foreign_key_unknown_target_column`, `foreign_key_column_count`, `foreign_key_target_not_key`, `foreign_key_type_mismatch`, `foreign_key_duplicate`; ссылка на себя и циклы корректны; устойчивый порядок; проверка — тесты фабрики и `tests/cli/test_validate.py`
- [ ] 1.5 Обновить `docs/model-format.md` (поля, правила, коды, порядок проверки, ограничения: NULL в уникальности, нет индексов под FK, нет `ON DELETE`) и пример `tests/fixtures/model/example.yaml` со связью и набором; `docs/domain.md` — снять ограничение «связей нет»; проверка — `tests/modeling/test_model_format_doc.py` зелёный

## 2. Diff, имена и changelog

- [ ] 2.1 Функция имён `fk_<таблица>_<hash8>` и `uq_<таблица>_<hash8>` с обрезкой таблицы до 51 символа; проверка — тесты на стабильность при перестановке и длину ≤ 63 для таблицы из 60 символов
- [ ] 2.2 `ModelDiff`: `AddUnique`, `DropUnique`, `AddForeignKey`, `DropForeignKey` по содержимому; FK удаляемых таблиц и FK на них — отдельными удалениями; наборы удаляемой таблицы не удаляются отдельно; порядок групп по дельте `forge-migration`; проверка — тесты `test_model_diff.py` по сценариям дельты
- [ ] 2.3 Рендер `addUniqueConstraint`, `addForeignKeyConstraint`, `dropUniqueConstraint` и `dropForeignKeyConstraint` с явным `rollback`; откат `dropTable` восстанавливает наборы таблицы; проверка — тест точного YAML и побайтовой повторяемости в `test_liquibase_changelog.py`
- [ ] 2.4 Ответ `forge generate`: виды `add_unique`, `drop_unique`, `add_foreign_key`, `drop_foreign_key`, поле `constraint`; удаление ограничений в `auto` без `allow_drop` не отклоняется; проверка — `test_generate_changelog.py` и `tests/cli/test_generate.py`
- [ ] 2.5 Обновить `docs/migration.md` (changeset ограничений, имена, порядок групп, удаление таблицы со связями, откат) и `docs/architecture.md`; проверка — `tests/migration/test_migration_doc.py` сверяет пример со связями с выводом `forge generate`

## 3. Откат ограничений

- [ ] 3.1 `ChangelogSummary` и читатель: добавляемые и удаляемые ограничения (вид, таблица, имя); проверка — тесты сводки в `test_liquibase_changelog.py`
- [ ] 3.2 `SchemaProbeInterface.constraint_exists` и реализация по `pg_constraint`; `RollbackAttemptUseCase` добавляет `foreign_key_absent`, `unique_absent`, `foreign_key_present`, `unique_present`; проверка — `test_rollback_attempt.py` на пройденные и непройденные проверки
- [ ] 3.3 Дополнить раздел «Проверка возврата» `docs/migration.md`; проверка — тест документа зелёный

## 4. Сверка ограничений

- [ ] 4.1 `ActualTable` с FK и наборами уникальности; интроспекция `pg_constraint` с раскрытием колонок через `pg_attribute`; проверка — `test_actual_schema.py` и интеграционный тест интроспекции на `lbfr-db-test`
- [ ] 4.2 `SchemaComparison`: `foreign_key_missing`, `foreign_key_unexpected`, `unique_missing`, `unique_unexpected`, сравнение по содержимому без имён, порядок по дельте; таблица `table_missing` не даёт расхождений ограничений; проверка — `test_schema_comparison.py` по сценариям дельты `forge-reconciliation`
- [ ] 4.3 Обновить `docs/reconciliation.md` (что сравнивается, виды расхождений, порядок, ограничения) и тест документа; проверка — `tests/reconciliation/test_reconciliation_doc.py` зелёный

## 5. Интеграционная проверка

- [ ] 5.1 Интеграционный цикл на `lbfr-db-test`: модель с FK на таблицу ниже по модели, ссылкой на себя и составным набором уникальности накатывается и сверяется без расхождений; проверка — `uv run pytest -m integration` зелёный
- [ ] 5.2 Интеграционный цикл удаления: попытка, удаляющая FK, набор и таблицу со связями, откатывается Liquibase с пройденными проверками `*_present`; проверка — `uv run pytest -m integration` зелёный
- [ ] 5.3 Прогнать проверки репозитория: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`; проверка — все команды завершаются кодом `0`

## Workflow follow-up

- Реализовывать после архивации `add-drop-operations` в ветке `release/v0.2.0`.
- Синхронизировать дельты и архивировать изменение `/opsx:archive` после ревью.
- Закрыть задачу GitHub #4 (LBFR-015) после слияния.
