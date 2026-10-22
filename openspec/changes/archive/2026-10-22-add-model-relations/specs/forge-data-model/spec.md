# Spec Delta

## MODIFIED Requirements

### Requirement: Таблица задаётся именем, колонками и первичным ключом
Каждый элемент `tables` MUST быть отображением с обязательными полями `name`, `columns`
и `primary_key` и MAY содержать поля `foreign_keys` и `unique`. Отсутствующее `foreign_keys`
или `unique` SHALL считаться пустым списком. Список `columns` MUST содержать хотя бы одну колонку.
Порядок колонок SHALL сохраняться, но смысла для схемы не несёт.

#### Scenario: Таблица без колонок
- **WHEN** у таблицы `tables[0]` пустой список `columns`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns`

#### Scenario: Таблица без первичного ключа
- **WHEN** у таблицы `tables[1]` нет поля `primary_key`
- **THEN** `forge validate` сообщает нарушение с путём `tables[1].primary_key`

#### Scenario: Модель без связей
- **WHEN** ни одна таблица модели не содержит `foreign_keys` и `unique`
- **THEN** модель корректна, как и до введения этих полей

## ADDED Requirements

### Requirement: Набор уникальности — непустой список колонок своей таблицы
Каждый элемент `unique` MUST быть непустым списком имён колонок той же таблицы без повторов.
Набор SHALL NOT совпадать по составу с первичным ключом таблицы или с другим набором `unique`
той же таблицы.

#### Scenario: Корректный набор
- **WHEN** таблица `customer` содержит `unique: [[email]]`, и колонка `email` в ней есть
- **THEN** модель корректна

#### Scenario: Неизвестная колонка
- **WHEN** `tables[0].unique[0]` равен `[email, phone]`, а колонки `phone` в таблице нет
- **THEN** `forge validate` сообщает нарушение `unique_unknown_column` с путём `tables[0].unique[0][1]`

#### Scenario: Пустой набор
- **WHEN** `tables[0].unique[0]` — пустой список
- **THEN** `forge validate` сообщает нарушение `empty_unique` с путём `tables[0].unique[0]`

#### Scenario: Повтор колонки в наборе
- **WHEN** `tables[0].unique[0]` равен `[code, code]`
- **THEN** `forge validate` сообщает нарушение `unique_duplicate_column` с путём `tables[0].unique[0][1]`

#### Scenario: Набор совпадает с первичным ключом
- **WHEN** у таблицы `primary_key: [id]` и `unique: [[id]]`
- **THEN** `forge validate` сообщает нарушение `unique_equals_primary_key` с путём `tables[0].unique[0]`

#### Scenario: Повтор набора
- **WHEN** у таблицы `unique: [[a, b], [b, a]]`
- **THEN** `forge validate` сообщает нарушение `unique_duplicate` с путём `tables[0].unique[1]`

### Requirement: Внешний ключ ссылается на ключ другой или той же таблицы
Каждый элемент `foreign_keys` MUST быть отображением ровно с полями `columns` и `references`,
а `references` — ровно с полями `table` и `columns`. Списки колонок MUST быть непустыми, без
повторов, равной длины; колонки FK MUST быть в своей таблице, целевая таблица — в модели,
колонки цели — в целевой таблице.

#### Scenario: Корректный внешний ключ
- **WHEN** таблица `invoice` содержит `foreign_keys: [{columns: [customer_id], references: {table: customer, columns: [id]}}]`, у `customer` `primary_key: [id]`, а типы колонок совпадают
- **THEN** модель корректна

#### Scenario: Неизвестная целевая таблица
- **WHEN** FK `tables[1].foreign_keys[0]` ссылается на таблицу `client`, которой нет в модели
- **THEN** `forge validate` сообщает нарушение `foreign_key_unknown_table` с путём `tables[1].foreign_keys[0].references.table`

#### Scenario: Неизвестная колонка FK
- **WHEN** в `tables[1].foreign_keys[0].columns` указана колонка `client_id`, которой нет в таблице
- **THEN** `forge validate` сообщает нарушение `foreign_key_unknown_column` с путём `tables[1].foreign_keys[0].columns[0]`

#### Scenario: Неизвестная колонка цели
- **WHEN** в `references.columns` FK указана колонка `uid`, которой нет в целевой таблице
- **THEN** `forge validate` сообщает нарушение `foreign_key_unknown_target_column` с путём `tables[1].foreign_keys[0].references.columns[0]`

#### Scenario: Разное число колонок
- **WHEN** FK содержит две колонки, а `references.columns` — одну
- **THEN** `forge validate` сообщает нарушение `foreign_key_column_count` с путём `tables[1].foreign_keys[0]`

#### Scenario: Пустой список колонок FK
- **WHEN** `tables[1].foreign_keys[0].columns` — пустой список
- **THEN** `forge validate` сообщает нарушение `empty_foreign_key` с путём `tables[1].foreign_keys[0].columns`

#### Scenario: Повтор колонки в FK
- **WHEN** `tables[1].foreign_keys[0].columns` равен `[a, a]`
- **THEN** `forge validate` сообщает нарушение `foreign_key_duplicate_column` с путём `tables[1].foreign_keys[0].columns[1]`

#### Scenario: Ссылка на свою таблицу
- **WHEN** таблица `category` содержит FK `parent_id` → `category.id`, а `id` — её первичный ключ
- **THEN** модель корректна

#### Scenario: Цикл ссылок
- **WHEN** таблица `a` ссылается на `b`, а `b` — на `a`, и обе ссылки корректны
- **THEN** модель корректна

#### Scenario: Действие при удалении
- **WHEN** у FK `tables[1].foreign_keys[0]` есть поле `on_delete`
- **THEN** `forge validate` сообщает нарушение `unknown_field` с путём `tables[1].foreign_keys[0].on_delete`

### Requirement: Цель внешнего ключа — ключ целевой таблицы
Набор `references.columns` MUST совпадать по составу с первичным ключом целевой таблицы либо
с одним из её наборов `unique`; порядок колонок цели задаёт пары с колонками FK и для совпадения
не важен. Тип каждой колонки FK с параметрами MUST совпадать с типом парной колонки цели.
FK с теми же колонками, целью и колонками цели SHALL NOT повторяться в таблице.

#### Scenario: Цель — не ключ
- **WHEN** FK ссылается на колонку `customer.email`, а у `customer` нет `unique: [[email]]`, и `email` не первичный ключ
- **THEN** `forge validate` сообщает нарушение `foreign_key_target_not_key` с путём `tables[1].foreign_keys[0].references.columns`

#### Scenario: Цель — набор уникальности
- **WHEN** FK ссылается на `customer.email`, а у `customer` есть `unique: [[email]]` и типы совпадают
- **THEN** модель корректна

#### Scenario: Составной ключ в другом порядке
- **WHEN** у цели `primary_key: [invoice_id, line_no]`, а FK ссылается на `[line_no, invoice_id]` с парными типами
- **THEN** модель корректна

#### Scenario: Типы не совпадают
- **WHEN** колонка FK имеет тип `bigint`, а парная колонка цели — `integer`
- **THEN** `forge validate` сообщает нарушение `foreign_key_type_mismatch` с путём `tables[1].foreign_keys[0].columns[0]`

#### Scenario: Повтор внешнего ключа
- **WHEN** у таблицы два одинаковых FK
- **THEN** `forge validate` сообщает нарушение `foreign_key_duplicate` с путём второго FK

### Requirement: Связи проверяются после всех таблиц
Проверка внешних ключей MUST выполняться после проверки всех таблиц модели, и таблица со
структурными нарушениями или некорректным первичным ключом SHALL NOT считаться целью,
пригодной для проверки FK. Порядок нарушений MUST оставаться устойчивым.

#### Scenario: Ссылка на таблицу ниже по модели
- **WHEN** `tables[0]` ссылается FK на `tables[1]`, и обе таблицы корректны
- **THEN** модель корректна

#### Scenario: Повторная проверка
- **WHEN** модель с нарушениями FK и уникальности проверяется дважды
- **THEN** списки нарушений совпадают побайтово
