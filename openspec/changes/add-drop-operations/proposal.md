# Proposal

## Why

Liquibase Forge принимает только добавляющие изменения: модель попытки, в которой нет таблицы
или колонки из принятой модели, `forge generate` отклоняет кодом `1`. Поэтому удалить из схемы
объект, однажды принятый forge, нельзя. Задача LBFR-014 (GitHub #3) снимает это ограничение
для удаления таблиц и колонок, сохраняя откат неуспешной попытки и защиту от разрушающих
изменений в режиме `auto`.

## What Changes

- `forge generate` строит из удалённой таблицы changeset `dropTable`, из удалённой колонки
  существующей таблицы — `dropColumn`. Каждый такой changeset несёт явный блок `rollback`,
  восстанавливающий структуру объекта по принятой модели; данные не восстанавливаются.
- Порядок changeset: сначала удаления в порядке принятой модели (таблицы, затем колонки),
  затем добавления в порядке модели попытки; нумерация `id` сквозная.
- В ответе `forge generate` появляются виды changeset `drop_table` и `drop_column`; коды
  `table_removed` и `column_removed` уходят из перечня отказов `non_additive`. Смена типа,
  допустимости NULL и первичного ключа, в том числе удаление колонки первичного ключа,
  по-прежнему отклоняются.
- Признак согласия на удаления `allow_drop`: навык принимает ключ `--allow-drop` только вместе
  с `--mode auto`, шаблоны `forge-model` и `forge-apply` пишут `allow_drop` во фронтматтер.
  В режиме `auto` без согласия `forge generate` отклоняет удаления кодом `2` с видом ошибки
  `drop_not_allowed`: операция останавливается, попытка не расходуется.
- В режиме `interactive` удаления разрешены; стоп-знак перед накатом показывает их отдельным
  перечнем с предупреждением о потере данных.
- `forge rollback` подтверждает возврат удалённых объектов проверками `table_present`
  и `column_present`.
- `forge status` и `forge report` показывают `allow_drop`; отчёт дополнительно перечисляет
  удаления итогового changelog в поле `destructive`.
- Шаблоны: `forge-model` 1.1.0 → 1.2.0, `forge-apply` 1.2.0 → 1.3.0.

## Capabilities

### New Capabilities

Нет.

### Modified Capabilities

- `forge-migration`: построение changelog с удалениями и блоками `rollback`, порядок changeset,
  перечень отказов без удалений, отказ `drop_not_allowed`, проверка возврата удалённых объектов.
- `forge-operation`: признак `allow_drop` в навыке и шаблонах, перечень удалений на стоп-знаке
  перед накатом, условие гейта перед накатом без требования «только добавляющие изменения».
- `forge-operation-commands`: `allow_drop` в ответах `forge status` и `forge report`, перечень
  `destructive` в отчёте.

## Impact

- Код: `src/forge/migration/` (domain: diff и изменения схемы; infrastructure: запись и чтение
  changelog, чтение фронтматтера; application: сценарии построения и отката),
  `src/forge/operation/` (чтение фронтматтера, представление операции, отчёт и контракт чтения
  результатов попытки), `src/forge/cli/commands/` (`generate`, `status`, `report`).
- Шаблоны `templates/forge-model.md`, `templates/forge-apply.md`, навык `.claude/skills/forge/SKILL.md`.
- Документы: `docs/domain.md`, `docs/model-format.md`, `docs/migration.md`, `docs/architecture.md`,
  `docs/operation.md`.
- Тесты: модульные тесты миграции и операции, `tests/operation/test_templates.py`, интеграционные
  тесты на `lbfr-db-test`, тест примера в `docs/migration.md`.
- Совместимость: JSON-поле `non_additive` сохраняется; беклоги, порождённые прежними версиями
  шаблонов, исполняются как `allow_drop: false`. Принятые changelog с удалениями остаются
  в `master.yaml` навсегда: запасной путь отката накатывает их при пересоздании БД.
