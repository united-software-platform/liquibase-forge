# forge-reconciliation Specification

## Purpose

Сверка результата попытки: фактическая схема тестовой БД сравнивается с моделью данных,
а журнал Liquibase — с changelog попытки, чтобы вердикт попытки опирался на состояние БД,
а не на исход наката.

## Requirements

### Requirement: Сверка сравнивает фактическую схему с моделью
`forge reconcile --model <модель> --changelog <changelog>` MUST читать фактическую схему `public`
целевой БД из `FORGE_DB_*` интроспекцией каталога PostgreSQL, а не из changelog. Таблицы журнала
Liquibase SHALL исключаться из сравнения.

#### Scenario: Схема совпадает с моделью
- **WHEN** changelog модели со всеми десятью типами формата накатан и других таблиц в БД нет
- **THEN** команда возвращает код `0`, перечень расхождений пуст

#### Scenario: Служебные таблицы Liquibase
- **WHEN** в БД есть `databasechangelog` и `databasechangeloglock`
- **THEN** они не считаются лишними таблицами

### Requirement: Таблицы и колонки сверяются в обе стороны
Таблица или колонка модели, которой нет в БД, MUST давать расхождение `table_missing`
либо `column_missing`. Таблица или колонка в БД, которой нет в модели, SHALL давать
`table_unexpected` либо `column_unexpected`. Порядок колонок MUST NOT сравниваться.

#### Scenario: Лишняя колонка
- **WHEN** в таблице `customer` БД есть колонка `legacy`, которой нет в модели
- **THEN** перечень содержит расхождение `column_unexpected` для `customer.legacy`

#### Scenario: Отсутствующая таблица
- **WHEN** таблицы модели `invoice` в БД нет
- **THEN** перечень содержит `table_missing` для `invoice` и не содержит расхождений её колонок

#### Scenario: Другой порядок колонок
- **WHEN** колонки таблицы в БД идут в другом порядке, чем в модели
- **THEN** расхождений нет

### Requirement: Колонка сверяется по типу и допустимости NULL
Для колонки, которая есть и в модели, и в БД, тип с параметрами MUST совпадать с отображением
типа модели в PostgreSQL, иначе — расхождение `column_type_mismatch`. Итоговая допустимость NULL
SHALL совпадать, иначе — `column_nullable_mismatch`. Тип PostgreSQL вне отображения формата MUST
давать `column_type_mismatch` с фактическим типом в расхождении.

#### Scenario: Другая длина строки
- **WHEN** в модели `email` — `string` с `length: 255`, а в БД `varchar(320)`
- **THEN** перечень содержит `column_type_mismatch` с ожидаемым `string(255)` и фактическим `string(320)`

#### Scenario: Колонка допускает NULL вопреки модели
- **WHEN** в модели колонка NOT NULL, а в БД допускает NULL
- **THEN** перечень содержит `column_nullable_mismatch`

#### Scenario: Тип вне формата
- **WHEN** колонка в БД имеет тип `smallint`
- **THEN** перечень содержит `column_type_mismatch`, где фактическое значение — `smallint`

### Requirement: Первичный ключ сверяется как упорядоченный список колонок
Первичный ключ таблицы в БД MUST совпадать с `primary_key` модели по составу и порядку колонок.
Имя ограничения SHALL NOT сравниваться. Отсутствие ключа в БД MUST давать расхождение
`primary_key_mismatch`.

#### Scenario: Ключ в другом порядке
- **WHEN** в модели `primary_key: [invoice_id, line_no]`, а в БД ключ по `line_no, invoice_id`
- **THEN** перечень содержит `primary_key_mismatch`

#### Scenario: Имя ограничения отличается
- **WHEN** ключ в БД совпадает по колонкам, но называется не `pk_<таблица>`
- **THEN** расхождений нет

### Requirement: Каждый changeset попытки записан Liquibase как исполненный
Для каждого changeset changelog попытки в `DATABASECHANGELOG` MUST быть запись с тем же `id`,
`author` и `filename`, равным `logicalFilePath`, и `EXECTYPE = EXECUTED`. Иначе SHALL давать
расхождение `changeset_not_executed`.

#### Scenario: Changeset не записан
- **WHEN** второго changeset попытки нет в журнале
- **THEN** перечень содержит `changeset_not_executed` для его `id`

#### Scenario: Changeset помечен, но не исполнен
- **WHEN** запись changeset имеет `EXECTYPE = MARK_RAN`
- **THEN** перечень содержит `changeset_not_executed` с фактическим значением `MARK_RAN`

#### Scenario: Пустой changelog
- **WHEN** changelog попытки не содержит changeset
- **THEN** проверка журнала не даёт расхождений

### Requirement: Результат сверки пишется в reconcile.json
Команда MUST печатать один JSON-объект с вердиктом и перечнем расхождений и писать
`reconcile.json` рядом с changelog. Каждое расхождение SHALL содержать вид, таблицу, колонку
или `id` changeset, ожидаемое и фактическое значение и сообщение. Порядок расхождений MUST
быть устойчивым.

#### Scenario: Расхождения найдены
- **WHEN** сверка нашла хотя бы одно расхождение
- **THEN** команда возвращает код `1`, вердикт `failure`, `reconcile.json` записан с тем же перечнем

#### Scenario: Повторная сверка
- **WHEN** сверка дважды выполнена на неизменной БД
- **THEN** перечни расхождений совпадают

### Requirement: Ошибка окружения не даёт вердикта
Не заданные переменные окружения, БД вне перечня тестовых, недоступная БД, нечитаемая или
некорректная модель и нечитаемый changelog MUST давать код `2` без `reconcile.json`.

#### Scenario: БД недоступна
- **WHEN** целевая БД не принимает подключения
- **THEN** команда возвращает код `2`, `reconcile.json` не записан

#### Scenario: БД вне перечня
- **WHEN** `FORGE_DB_*` указывает на БД вне `FORGE_TEST_DB_ALLOWLIST`
- **THEN** команда возвращает код `2`, к БД не подключается
