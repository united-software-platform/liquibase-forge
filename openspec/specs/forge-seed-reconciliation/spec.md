# forge-seed-reconciliation Specification

## Purpose

Вердикт попытки seed Liquibase Forge: команда `forge reconcile-seed` сравнивает фактические строки
таблиц seed с seed попытки и проверяет запись Liquibase о changeset попытки.

## Requirements

### Requirement: Сверка сравнивает строки таблиц seed с seed попытки
`forge reconcile-seed` MUST читать строки каждой таблицы seed попытки из целевой БД и сравнивать
их с seed по PK. Значения из БД SHALL приводиться к нормализованной форме формата seed по типу
колонки модели. Вердикт `success` MUST выноситься только при пустом перечне расхождений.

#### Scenario: Строки совпадают
- **WHEN** после наката строки таблицы `order_status` совпадают с seed попытки по всем колонкам
- **THEN** команда возвращает код `0` с вердиктом `success`

#### Scenario: Одно значение в разной записи
- **WHEN** в seed `valid_from: "2026-01-01T03:00:00+03:00"`, а в БД момент `2026-01-01 00:00:00+00`
- **THEN** расхождения нет

### Requirement: Строки сверяются в обе стороны
Строка seed без строки БД с тем же PK MUST давать расхождение `row_missing`. Строка БД с PK,
которого нет в seed, MUST давать `row_unexpected`: таблица seed принадлежит seed целиком.

#### Scenario: Строка не вставлена
- **WHEN** seed попытки содержит строку `paid`, а в `order_status` её нет
- **THEN** перечень содержит `row_missing` с таблицей `order_status` и ключом `paid`

#### Scenario: Лишняя строка
- **WHEN** в `order_status` есть строка `legacy`, которой нет в seed попытки
- **THEN** перечень содержит `row_unexpected` с ключом `legacy` и фактическими значениями строки

### Requirement: Значения строки сверяются по колонкам
Для строки, найденной по PK, каждая колонка таблицы MUST совпадать с seed в нормализованной форме;
колонка без ключа в seed ожидается NULL. Отличие SHALL давать одно расхождение `value_mismatch`
на колонку с ожидаемым и фактическим значением.

#### Scenario: Значение отличается
- **WHEN** в seed `title: Черновик`, а в БД у строки `draft` — `Набросок`
- **THEN** перечень содержит `value_mismatch` с колонкой `title`, ожидаемым `Черновик` и фактическим `Набросок`

#### Scenario: Ожидался NULL
- **WHEN** в seed у строки нет ключа `description`, а в БД у неё `description` не NULL
- **THEN** перечень содержит `value_mismatch` с ожидаемым `null`

### Requirement: Таблица, убранная из seed, пуста после наката
Таблица, которая есть в принятом seed и отсутствует в seed попытки, MUST сверяться как таблица
без строк: каждая её строка SHALL давать `row_unexpected`. Без `--accepted-seed` принятым seed
служит `seed.yaml` корня принятого состояния; нет файла — принятый seed пуст.

#### Scenario: Справочник убран, строки остались
- **WHEN** принятый seed содержит `legacy_status`, seed попытки — нет, а в таблице осталась строка `old`
- **THEN** перечень содержит `row_unexpected` для `legacy_status` с ключом `old`

### Requirement: Таблицы вне seed не сверяются
Таблица модели, которой нет ни в seed попытки, ни в принятом seed, MUST NOT читаться сверкой
seed, и её строки SHALL NOT давать расхождений.

#### Scenario: Пользовательская таблица
- **WHEN** в таблице `customer`, которой нет в seed, есть строки
- **THEN** сверка seed их не читает и расхождений по `customer` не даёт

### Requirement: Каждый changeset данных записан Liquibase как исполненный
Для каждого changeset changelog попытки в `DATABASECHANGELOG` MUST быть запись с тем же `id`,
`author`, `filename`, равным `logicalFilePath`, и `EXECTYPE = EXECUTED`. Иначе SHALL давать
расхождение `changeset_not_executed`, как у `forge reconcile`.

#### Scenario: Changeset данных не записан
- **WHEN** второго changeset changelog данных нет в журнале
- **THEN** перечень содержит `changeset_not_executed` для его `id`

### Requirement: Расхождения seed идут в устойчивом порядке
Порядок MUST быть таким: таблицы seed попытки в порядке seed; внутри таблицы — строки seed
по порядку с `row_missing` или `value_mismatch` по колонкам модели, затем лишние строки по
возрастанию PK; затем таблицы, убранные из seed, в порядке принятого seed; затем changeset в
порядке changelog. Повторная сверка неизменной БД SHALL давать тот же перечень.

#### Scenario: Повторная сверка
- **WHEN** сверка дважды выполнена на неизменной БД
- **THEN** перечни расхождений совпадают побайтово

### Requirement: Результат сверки seed пишется в reconcile.json
Команда MUST печатать один JSON-объект с полями `seed`, `changelog`, `database`, `verdict`
и `discrepancies` и писать его в `reconcile.json` рядом с changelog. Расхождение SHALL содержать
`kind`, `table`, `key`, `column`, `changeset`, `expected`, `actual` и `message`. `key` — PK строки
отображением «колонка → значение» либо `null`.

#### Scenario: Расхождения найдены
- **WHEN** сверка нашла `row_missing`
- **THEN** команда возвращает `1` с вердиктом `failure`, `reconcile.json` записан с тем же перечнем, `key` расхождения — `{"code": "paid"}`

### Requirement: Ошибка окружения не даёт вердикта сверки seed
Не заданные переменные окружения, БД вне перечня тестовых, недоступная БД, нечитаемые или
некорректные seed, принятый seed, модель и changelog MUST давать код `2` без `reconcile.json`.
Целевая БД MUST проверяться по `FORGE_TEST_DB_ALLOWLIST` до подключения.

#### Scenario: Seed попытки некорректен
- **WHEN** seed попытки не проходит `forge validate-seed`
- **THEN** команда возвращает код `2` с видом ошибки `seed_invalid`, `reconcile.json` не записан

#### Scenario: БД вне перечня
- **WHEN** `FORGE_DB_*` указывает на БД вне `FORGE_TEST_DB_ALLOWLIST`
- **THEN** команда возвращает код `2` и к БД не подключается
