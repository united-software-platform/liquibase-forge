# forge-data-model Specification

## Purpose

Формат файла модели данных Liquibase Forge и его проверка командой `forge validate`: агент описывает
целевое состояние схемы независимо от PostgreSQL и до наката узнаёт все нарушения модели сразу.

## Requirements

### Requirement: Модель данных описывается файлом YAML версии 1
Модель данных MUST задаваться файлом YAML, корень которого — отображение ровно с двумя полями:
`version` со значением `1` и `tables` со списком таблиц. Список таблиц MAY быть пустым. Модель
SHALL описывать полное целевое состояние схемы `public`, а не изменение.

#### Scenario: Минимальная модель
- **WHEN** файл содержит `version: 1` и `tables: []`
- **THEN** `forge validate` признаёт модель корректной

#### Scenario: Неподдерживаемая версия
- **WHEN** поле `version` отсутствует или его значение не целое число `1`
- **THEN** `forge validate` сообщает нарушение с путём `version`, а таблицы не проверяет

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

### Requirement: Колонка задаётся именем, типом и допустимостью NULL
Каждый элемент `columns` MUST быть отображением с полями `name` и `type` и MAY содержать `nullable`
и параметры своего типа. Значение `nullable` MUST быть логическим; без него колонка SHALL
допускать NULL.

#### Scenario: Колонка без nullable
- **WHEN** колонка `email` типа `text` вне первичного ключа не содержит `nullable`
- **THEN** модель корректна, и колонка допускает NULL

#### Scenario: nullable не логическое
- **WHEN** у колонки `tables[0].columns[2]` задано `nullable: "no"`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[2].nullable`

### Requirement: Тип колонки берётся из перечня формата
Тип MUST быть одним из: `integer`, `bigint`, `boolean`, `string`, `text`, `decimal`, `date`,
`timestamp`, `timestamp_tz`, `uuid`. Тип `string` MUST иметь целый `length` от 1 до 10485760.
Тип `decimal` MUST иметь целый `precision` от 1 до 1000 и целый `scale` от 0 до `precision`.
Параметр, не относящийся к типу колонки, SHALL быть нарушением.

#### Scenario: Строка без длины
- **WHEN** колонка `tables[0].columns[1]` имеет `type: string` без `length`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[1].length`

#### Scenario: Масштаб больше точности
- **WHEN** колонка `tables[0].columns[3]` имеет `type: decimal`, `precision: 5`, `scale: 6`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[3].scale`

#### Scenario: Параметр чужого типа
- **WHEN** колонка `tables[0].columns[0]` имеет `type: integer` и `length: 10`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[0].length`

#### Scenario: Неизвестный тип
- **WHEN** колонка `tables[0].columns[0]` имеет `type: varchar`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[0].type`

### Requirement: Имена таблиц и колонок — допустимые идентификаторы
Имена таблиц и колонок MUST соответствовать шаблону `^[a-z][a-z0-9_]{0,62}$` и SHALL NOT быть
зарезервированными словами PostgreSQL. Имя таблицы MUST быть не длиннее 60 символов и SHALL NOT
совпадать с именами таблиц журнала Liquibase. Имя колонки SHALL NOT совпадать с именем системной
колонки PostgreSQL.

#### Scenario: Имя с заглавной буквой
- **WHEN** таблица `tables[0]` называется `Customer`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].name`

#### Scenario: Зарезервированное слово
- **WHEN** таблица `tables[0]` называется `order`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].name`

#### Scenario: Имя таблицы длиннее 60 символов
- **WHEN** имя таблицы `tables[0]` состоит из 61 символа и соответствует шаблону
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].name`

#### Scenario: Имя системной колонки
- **WHEN** колонка `tables[0].columns[1]` называется `xmin`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[1].name`

### Requirement: Имена уникальны в своей области
Имена таблиц MUST быть уникальны в модели, имена колонок — в пределах таблицы. Нарушение SHALL
указывать путь второго и каждого следующего вхождения имени.

#### Scenario: Повтор имени колонки
- **WHEN** в таблице `tables[0]` колонки `columns[0]` и `columns[2]` обе называются `id`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[2].name`

#### Scenario: Повтор имени таблицы
- **WHEN** таблицы `tables[0]` и `tables[1]` обе называются `customer`
- **THEN** `forge validate` сообщает нарушение с путём `tables[1].name`

### Requirement: Первичный ключ — непустой упорядоченный список колонок таблицы
`primary_key` MUST быть непустым списком имён колонок той же таблицы без повторов. Порядок
колонок первичного ключа SHALL быть значимым. Колонки первичного ключа SHALL быть NOT NULL
независимо от `nullable`, а явное `nullable: true` у такой колонки MUST быть нарушением.

#### Scenario: Ссылка на несуществующую колонку
- **WHEN** `tables[0].primary_key` равен `[id, code]`, а колонки `code` в таблице нет
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].primary_key[1]`

#### Scenario: Колонка ключа объявлена допускающей NULL
- **WHEN** колонка `tables[0].columns[0]` входит в первичный ключ и имеет `nullable: true`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[0].nullable`

#### Scenario: Колонка ключа без nullable
- **WHEN** колонка первичного ключа не содержит `nullable`
- **THEN** модель корректна, и колонка считается NOT NULL

### Requirement: Структура файла строгая
Неизвестное поле, повторный ключ в одном отображении и значение не того вида (строка вместо
списка, число вместо строки, логическое вместо числа) MUST быть нарушениями. Синтаксическая ошибка
YAML MUST давать нарушение с указанием строки и столбца.

#### Scenario: Неизвестное поле
- **WHEN** у колонки `tables[0].columns[0]` есть поле `default`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[0].default`

#### Scenario: Повторный ключ
- **WHEN** в отображении колонки `tables[0].columns[1]` ключ `type` встречается дважды
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[1].type`, а не берёт молча последнее значение

#### Scenario: Логическое значение вместо числа
- **WHEN** у колонки `tables[0].columns[1]` задано `length: true`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[1].length`

#### Scenario: Синтаксическая ошибка YAML
- **WHEN** файл модели не разбирается как YAML
- **THEN** `forge validate` возвращает код `1` и одно нарушение с номером строки и столбца ошибки

### Requirement: forge validate возвращает все нарушения сразу
Команда `forge validate --model <путь>` MUST печатать один JSON-объект с путём модели, признаком
корректности и списком нарушений; каждое нарушение SHALL содержать путь, код и сообщение. Таблица
со структурными нарушениями MUST исключаться из проверки инвариантов, остальные таблицы SHALL
проверяться полностью.

#### Scenario: Корректная модель
- **WHEN** модель не содержит нарушений
- **THEN** команда возвращает код `0`, признак корректности `true` и пустой список нарушений

#### Scenario: Несколько нарушений в разных таблицах
- **WHEN** у таблицы `tables[0]` неизвестное поле, а в таблице `tables[1]` первичный ключ ссылается на несуществующую колонку
- **THEN** команда возвращает код `1` и оба нарушения в одном списке

#### Scenario: Порядок нарушений устойчив
- **WHEN** команда дважды проверяет один и тот же файл
- **THEN** списки нарушений совпадают побайтово

### Requirement: Нечитаемый файл модели — ошибка вызова
Если файл модели не существует, является каталогом, не читается или не является текстом UTF-8,
`forge validate` MUST вернуть код `2` и JSON-объект ошибки вызова, а не перечень нарушений.

#### Scenario: Файла нет
- **WHEN** `forge validate --model backlog/missing.yaml` вызвана для несуществующего файла
- **THEN** команда возвращает код `2` и JSON-объект ошибки с указанием пути

#### Scenario: Аргумент не передан
- **WHEN** `forge validate` вызвана без `--model`
- **THEN** команда возвращает код `2` и JSON-объект ошибки вызова

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
