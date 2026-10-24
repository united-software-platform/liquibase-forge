# Proposal

## Why

После `add-seed-format` seed можно описать и проверить, но в БД ему не попасть: `forge generate`
строит changelog только из разницы моделей, а откат и его проверка знают только структуру. Это
вторая из четырёх частей операции seed (LBFR-028, #20): changelog данных, его накат существующей
командой `forge apply` и откат с проверкой возврата строк.

## What Changes

- Новая команда `forge generate-seed --seed <seed попытки> [--accepted-seed <путь>] [--model <путь>] --operation <беклог операции> --out <changelog>`.
  Она строит changelog данных как разницу принятого seed и seed попытки:
  - новые строки — `insert`;
  - строки с тем же PK и другими значениями — `update`;
  - исчезнувшие строки и все строки таблицы, убранной из seed, — `delete`.
- Порядок changeset: вставки от целевых строк к зависимым, затем изменения, затем удаления
  от зависимых к целевым. Соседние строки одной таблицы и вида собираются в один changeset.
- У каждого changeset данных явный блок `rollback`, построенный из принятого seed.
- Изменения, которые нельзя выполнить ни в каком порядке, отклоняются кодом `1` с перечнем
  `unsupported`. Это временное нарушение `unique`, например обмен значениями набора
  уникальности. Это и изменение значения набора `unique`, на который ведёт внешний ключ, когда
  на прежнее значение ссылаются другие строки или новое занимают вставляемые или изменяемые строки.
- Удаления строк перечисляются в ответе. В режиме `auto` без согласия операции они отклоняются
  кодом `2` с видом `drop_not_allowed`, как удаления таблиц.
- `forge rollback` понимает changelog данных: проверка возврата получает проверки строк
  `row_absent`, `row_present` и `row_restored`.
- Отклонение от решения Q11 обсуждения: в Q11 был порядок «удаления → изменения → вставки». Он
  ломает типовой сценарий «вывести строку справочника и перевести ссылки на новую», поэтому
  порядок заменён (см. `design.md`).

## Capabilities

### New Capabilities

- `forge-seed-migration`: построение changelog данных из разницы seed командой
  `forge generate-seed`, порядок и состав changeset данных, явный откат.

### Modified Capabilities

- `forge-migration`: проверка возврата `forge rollback` дополняется проверками строк для
  changelog данных. Существующие проверки структуры не меняются.

## Impact

- Код:
  - новый домен разницы seed в `src/forge/seeding/domain/`;
  - сценарий `GenerateSeedChangelogUseCase` в `src/forge/seeding/application/`;
  - отрисовка changelog данных в `src/forge/seeding/infrastructure/`;
  - подкоманда `src/forge/cli/commands/generate_seed.py`;
  - чтение changelog данных и проверки строк в `src/forge/migration/` (откат).
- Тесты: модульные `tests/seeding/`, `tests/migration/`, `tests/cli/test_generate_seed.py`;
  интеграционные — накат и откат seed со значениями всех десяти типов на `lbfr-db-test`.
- Документация: `docs/seed-migration.md`, разделы «Откат» и «Проверка возврата»
  `docs/migration.md`, таблица команд `docs/architecture.md`.
- Шлюз Liquibase, `forge apply` и запасной путь не меняются.
