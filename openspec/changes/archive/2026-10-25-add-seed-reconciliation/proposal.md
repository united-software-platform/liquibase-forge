# Proposal

## Why

После `add-seed-migration` changelog данных накатывается и откатывается, но вердикта попытки нет:
`forge reconcile` сверяет только структуру и журнал, а строки не видит. Это третья из четырёх
частей операции seed (LBFR-028, #20). Сверка строк — условие вердикта `success` попытки seed
и источник плана правки seed для следующей попытки.

## What Changes

- Новая команда `forge reconcile-seed --seed <seed попытки> --changelog <changelog попытки> [--accepted-seed <путь>] [--model <путь>]`.
  Она сравнивает фактические строки таблиц seed с seed попытки по PK в нормализованной форме
  и проверяет журнал Liquibase по changeset попытки так же, как `forge reconcile`.
- Таблица, убранная из seed относительно принятого seed, после наката MUST быть пустой.
  Её оставшиеся строки — расхождения.
- Новые виды расхождений:
  - `row_missing` — строки seed нет в БД;
  - `row_unexpected` — в таблице seed лишняя строка;
  - `value_mismatch` — колонка строки отличается от seed.
- Результат пишется в `reconcile.json` каталога попытки. Каждое расхождение получает новое поле
  `key` — PK строки. Для расхождений журнала `key` равно `null`.
- Структура схемы этой командой не сверяется: seed её не меняет (решение Q13).

## Capabilities

### New Capabilities

- `forge-seed-reconciliation`: сверка строк таблиц seed и журнала Liquibase после наката
  changelog данных командой `forge reconcile-seed`, виды расхождений строк и их порядок.

### Modified Capabilities

Нет. `forge reconcile` и формат его ответа не меняются.

## Impact

- Код:
  - чтение строк таблиц seed через `psycopg` с нормализацией по типам модели
    в `src/forge/seeding/infrastructure/`;
  - доменное сравнение строк в `src/forge/seeding/domain/`;
  - сценарий `ReconcileSeedUseCase`;
  - подкоманда `src/forge/cli/commands/reconcile_seed.py`.
- Переиспользуется из «Сверки»:
  - проверка журнала `JournalCheck` и чтение журнала — через контракты приложения;
  - расхождение `Discrepancy` — расширяется необязательным полем `key`.
- Тесты: модульные `tests/seeding/`, `tests/cli/test_reconcile_seed.py`, интеграционный цикл
  «накат → сверка» со всеми десятью типами на `lbfr-db-test`.
- Документация: `docs/seed-reconciliation.md`, таблица команд `docs/architecture.md`.
