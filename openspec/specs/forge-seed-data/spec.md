# forge-seed-data Specification

## Purpose

Формат файла seed справочных данных Liquibase Forge и его проверка командой `forge validate-seed`:
агент описывает полное целевое состояние строк справочных таблиц и до наката узнаёт все нарушения
seed относительно модели данных сразу.

## Requirements

### Requirement: Seed описывается файлом YAML версии 1
Seed MUST задаваться файлом YAML, корень которого — отображение ровно с двумя полями: `version`
со значением `1` и `tables` со списком таблиц. Список таблиц MAY быть пустым. Seed SHALL описывать
полное целевое состояние строк своих таблиц, а не изменение.

#### Scenario: Пустой seed
- **WHEN** файл содержит `version: 1` и `tables: []`
- **THEN** `forge validate-seed` признаёт seed корректным

#### Scenario: Неподдерживаемая версия
- **WHEN** поле `version` отсутствует или его значение не целое число `1`
- **THEN** `forge validate-seed` сообщает нарушение `unsupported_version` или `missing_field` с путём `version` и таблицы не проверяет

#### Scenario: Неизвестное поле корня
- **WHEN** корень содержит поле `data`
- **THEN** `forge validate-seed` сообщает нарушение `unknown_field` с путём `data`

### Requirement: Таблица seed задаётся именем и строками
Каждый элемент `tables` MUST быть отображением ровно с полями `name` и `rows`; `rows` MUST быть
списком строк и MAY быть пустым. Таблица SHALL встречаться в seed не больше одного раза и MUST
быть таблицей модели данных.

#### Scenario: Пустой список строк
- **WHEN** таблица `order_status` модели указана в seed с `rows: []`
- **THEN** seed корректен, и таблица `order_status` принадлежит seed без строк

#### Scenario: Таблицы нет в модели
- **WHEN** `tables[0].name` равно `order_state`, а такой таблицы в модели нет
- **THEN** `forge validate-seed` сообщает нарушение `unknown_table` с путём `tables[0].name`, строки этой таблицы не проверяются

#### Scenario: Повтор таблицы
- **WHEN** таблица `order_status` указана в `tables[0]` и `tables[2]`
- **THEN** `forge validate-seed` сообщает нарушение `duplicate_table` с путём `tables[2].name`

### Requirement: Таблица seed принадлежит seed целиком
Строки таблицы, указанной в seed, SHALL составлять её полное содержимое: любая строка БД вне seed
считается лишней. Таблицы модели, не указанные в seed, seed не касаются.

#### Scenario: Таблица вне seed
- **WHEN** в модели есть таблицы `customer` и `order_status`, а seed указывает только `order_status`
- **THEN** seed корректен и не задаёт содержимого таблицы `customer`

### Requirement: Строка задаётся значениями колонок
Каждая строка MUST быть отображением «имя колонки → значение». Имя MUST быть колонкой таблицы
в модели. Колонка без ключа в строке SHALL считаться NULL. Значение `null` SHALL быть явным NULL.

#### Scenario: Неизвестная колонка
- **WHEN** строка `tables[0].rows[1]` содержит ключ `label`, а у таблицы нет колонки `label`
- **THEN** `forge validate-seed` сообщает нарушение `unknown_column` с путём `tables[0].rows[1].label`

#### Scenario: Пропущенная колонка, допускающая NULL
- **WHEN** у колонки `description` нет `nullable: false`, и строка не содержит ключ `description`
- **THEN** seed корректен, и значение `description` в строке — NULL

### Requirement: NOT NULL и первичный ключ требуют значения
Колонка с итоговой допустимостью NOT NULL, включая каждую колонку первичного ключа, MUST иметь
в каждой строке значение, отличное от NULL. Пропуск ключа и явный `null` SHALL быть одним
нарушением `null_value`.

#### Scenario: Нет значения первичного ключа
- **WHEN** первичный ключ таблицы — `[code]`, а строка `tables[0].rows[0]` не содержит `code`
- **THEN** `forge validate-seed` сообщает нарушение `null_value` с путём `tables[0].rows[0].code`

#### Scenario: Явный NULL в NOT NULL колонке
- **WHEN** у колонки `title` задано `nullable: false`, а в строке `tables[0].rows[2]` указано `title: null`
- **THEN** `forge validate-seed` сообщает нарушение `null_value` с путём `tables[0].rows[2].title`

### Requirement: Целые и логические значения записываются значениями YAML
Значение колонки `integer` MUST быть целым числом YAML от −2147483648 до 2147483647, колонки
`bigint` — от −9223372036854775808 до 9223372036854775807. Значение колонки `boolean` MUST быть
логическим значением YAML. Строка, дробное число и значение другого вида SHALL быть нарушением.

#### Scenario: Число строкой
- **WHEN** колонка `sort_order` типа `integer`, а в строке указано `sort_order: "10"`
- **THEN** `forge validate-seed` сообщает нарушение `invalid_value` с путём строки и колонки

#### Scenario: Выход за диапазон integer
- **WHEN** колонка `sort_order` типа `integer`, а в строке указано `sort_order: 3000000000`
- **THEN** `forge validate-seed` сообщает нарушение `value_out_of_range`

### Requirement: Строковые значения записываются строками YAML
Значение колонок `string` и `text` MUST быть строкой YAML. Длина значения колонки `string`
в символах MUST NOT превышать её `length`. Число или логическое значение без кавычек SHALL быть
нарушением: неявного приведения нет.

#### Scenario: Строка длиннее length
- **WHEN** колонка `code` типа `string` с `length: 8`, а в строке указано `code: cancelled_by_user`
- **THEN** `forge validate-seed` сообщает нарушение `value_out_of_range`

#### Scenario: Число в строковой колонке
- **WHEN** колонка `code` типа `string`, а в строке указано `code: 404` без кавычек
- **THEN** `forge validate-seed` сообщает нарушение `invalid_value`

### Requirement: Значения decimal записываются без потери точности
Значение колонки `decimal` MUST быть строкой десятичной записи вида `-12.50` либо целым числом
YAML. Число цифр целой части MUST NOT превышать `precision − scale`, дробной — `scale`. Дробное
число YAML SHALL быть нарушением `invalid_value`: оно теряет точность.

#### Scenario: Десятичное значение строкой
- **WHEN** колонка `fee` типа `decimal` с `precision: 12`, `scale: 2`, а в строке указано `fee: "12.50"`
- **THEN** значение корректно

#### Scenario: Дробное число YAML
- **WHEN** колонка `fee` типа `decimal`, а в строке указано `fee: 12.5` без кавычек
- **THEN** `forge validate-seed` сообщает нарушение `invalid_value`

#### Scenario: Лишние знаки после запятой
- **WHEN** колонка `fee` типа `decimal` с `scale: 2`, а в строке указано `fee: "1.255"`
- **THEN** `forge validate-seed` сообщает нарушение `value_out_of_range`

### Requirement: Даты и моменты времени записываются в ISO 8601
Значение колонки `date` MUST иметь вид `YYYY-MM-DD`, колонки `timestamp` — `YYYY-MM-DDTHH:MM:SS`
с необязательной дробью до шести знаков и без смещения, колонки `timestamp_tz` — тот же вид
с обязательным смещением `Z` или `±HH:MM`. Значение MUST быть существующей календарной датой
и временем.

#### Scenario: Момент без смещения в timestamp_tz
- **WHEN** колонка `valid_from` типа `timestamp_tz`, а в строке указано `valid_from: "2026-01-01T00:00:00"`
- **THEN** `forge validate-seed` сообщает нарушение `invalid_value`

#### Scenario: Несуществующая дата
- **WHEN** колонка `starts_on` типа `date`, а в строке указано `starts_on: "2026-02-30"`
- **THEN** `forge validate-seed` сообщает нарушение `invalid_value`

#### Scenario: Дата без кавычек
- **WHEN** колонка `starts_on` типа `date`, а в строке указано `starts_on: 2026-02-28` без кавычек
- **THEN** значение корректно

### Requirement: UUID записывается в канонической форме
Значение колонки `uuid` MUST быть строкой из 32 шестнадцатеричных цифр в нижнем регистре,
разделённых дефисами по схеме 8-4-4-4-12. Генерации значений нет: каждый `uuid` в seed записан
литералом.

#### Scenario: UUID в верхнем регистре
- **WHEN** колонка `id` типа `uuid`, а в строке указано `id: "3F2504E0-4F89-41D3-9A0C-0305E82C3301"`
- **THEN** `forge validate-seed` сообщает нарушение `invalid_value`

### Requirement: Первичный ключ строки уникален в таблице
Значения первичного ключа MUST NOT повторяться в строках одной таблицы seed. Повтор SHALL
сообщаться на повторной строке.

#### Scenario: Повтор первичного ключа
- **WHEN** строки `tables[0].rows[0]` и `tables[0].rows[3]` имеют одинаковое значение PK `code: draft`
- **THEN** `forge validate-seed` сообщает нарушение `duplicate_primary_key` с путём `tables[0].rows[3]`

### Requirement: Наборы уникальности соблюдаются в seed
Значения колонок каждого набора `unique` таблицы MUST NOT повторяться в её строках. Строка, где
хотя бы одна колонка набора — NULL, в проверке этого набора SHALL NOT участвовать, как
в PostgreSQL.

#### Scenario: Повтор набора уникальности
- **WHEN** у таблицы набор `unique` `[title]`, и строки `rows[1]` и `rows[2]` имеют `title: Черновик`
- **THEN** `forge validate-seed` сообщает нарушение `duplicate_unique` с путём `tables[0].rows[2]`

#### Scenario: NULL в наборе уникальности
- **WHEN** у таблицы набор `unique` `[external_code]`, и две строки не содержат `external_code`
- **THEN** нарушения `duplicate_unique` нет

### Requirement: Внешний ключ таблицы seed ведёт на таблицу seed
Если таблица seed имеет внешний ключ, его целевая таблица MUST тоже быть указана в seed:
справочник не ссылается на пользовательские данные. Нарушение SHALL сообщаться один раз на внешний
ключ, а не на каждую строку.

#### Scenario: Цель FK вне seed
- **WHEN** таблица seed `order_status` имеет FK на `customer`, а `customer` в seed не указана
- **THEN** `forge validate-seed` сообщает нарушение `unseeded_reference_table` с путём `tables[0].name`

### Requirement: Значения внешнего ключа ссылаются на строки seed
Значения колонок FK строки MUST совпадать со значениями колонок цели в одной из строк целевой
таблицы seed. Строка, где хотя бы одна колонка FK — NULL, SHALL NOT проверяться по этому FK, как
в PostgreSQL.

#### Scenario: Ссылка на отсутствующую строку
- **WHEN** строка `tables[1].rows[0]` содержит `status_code: archived`, а в таблице-цели нет строки с `code: archived`
- **THEN** `forge validate-seed` сообщает нарушение `unresolved_reference` с путём `tables[1].rows[0]`

#### Scenario: NULL в колонке FK
- **WHEN** колонка FK `parent_code` допускает NULL и в строке не указана
- **THEN** нарушения `unresolved_reference` нет

### Requirement: Ссылки между строками seed не образуют цикл
Граф ссылок FK между строками seed MUST NOT содержать цикла длиннее одной строки: такой seed
нельзя вставить по строкам при ограничениях без отложенной проверки. Ссылка строки на саму себя
SHALL NOT считаться циклом.

#### Scenario: Цикл двух строк
- **WHEN** строка A таблицы `category` ссылается через `parent_code` на строку B, а строка B — на строку A
- **THEN** `forge validate-seed` сообщает нарушение `reference_cycle`, называющее строки цикла

#### Scenario: Ссылка на себя
- **WHEN** строка корневой категории ссылается через `parent_code` на собственный `code`
- **THEN** нарушения `reference_cycle` нет

### Requirement: Команда forge validate-seed проверяет seed по модели
Команда `forge validate-seed --seed <путь> [--model <путь>]` MUST проверять seed по модели данных.
Без `--model` моделью SHALL служить `model.yaml` корня принятого состояния; нет файла — модель
пуста. Команда SHALL печатать один JSON-объект с полями `seed`, `model`, `valid`, `violations`.

#### Scenario: Проверка по принятой модели
- **WHEN** `--model` не передан, а корень принятого состояния содержит `model.yaml`
- **THEN** seed проверяется по этой модели, и поле `model` ответа называет её путь

#### Scenario: Принятой модели нет
- **WHEN** `--model` не передан, а в корне принятого состояния нет `model.yaml`
- **THEN** модель пуста, и каждая таблица seed даёт нарушение `unknown_table`

### Requirement: Коды возврата forge validate-seed
Команда MUST возвращать `0`, если нарушений нет, `1`, если они есть, и `2` при ошибке входа:
seed или модель не прочитать, модель некорректна, корень принятого состояния задан неверно.
При коде `2` ответ SHALL быть объектом `error` с видом `seed_unreadable`, `model_unreadable`,
`model_invalid` или `accepted_root_invalid`.

#### Scenario: Некорректная модель
- **WHEN** модель, переданная `--model`, нарушает формат модели
- **THEN** команда возвращает `2` с видом ошибки `model_invalid`, а seed не проверяется

#### Scenario: Нет файла seed
- **WHEN** по пути `--seed` файла нет
- **THEN** команда возвращает `2` с видом ошибки `seed_unreadable`

### Requirement: Нарушения seed возвращаются все сразу в устойчивом порядке
Команда MUST возвращать все нарушения за один вызов: сначала структурные в порядке документа,
затем нарушения таблиц и строк в порядке документа, затем ссылки FK и циклы. Повторная проверка
того же seed по той же модели SHALL давать тот же ответ.

#### Scenario: Несколько нарушений в разных таблицах
- **WHEN** в `tables[0]` строка без значения PK, а в `tables[1]` значение `uuid` в верхнем регистре
- **THEN** ответ содержит оба нарушения, первым — нарушение `tables[0]`

#### Scenario: Повторная проверка
- **WHEN** команда дважды проверяет неизменный seed по неизменной модели
- **THEN** оба ответа совпадают побайтово

### Requirement: Значение колонки с перечнем входит в перечень
Значение колонки, у которой в модели задан `check`, MUST входить в её перечень. Значение вне
перечня SHALL давать нарушение `check_violated` с путём строки и колонки. NULL в колонке,
допускающей NULL, SHALL NOT нарушать перечень. Перечень проверяется только у значения, прошедшего
проверку типа.

#### Scenario: Значение вне перечня
- **WHEN** у колонки `order_status.code` задан `check: [draft, paid]`, а строка `tables[0].rows[2]` содержит `code: cancelled`
- **THEN** `forge validate-seed` сообщает нарушение `check_violated` с путём `tables[0].rows[2].code`

#### Scenario: Значение из перечня
- **WHEN** у колонки `order_status.code` задан `check: [draft, paid]`, а все строки содержат `draft` или `paid`
- **THEN** нарушений `check_violated` нет

#### Scenario: NULL в колонке с перечнем
- **WHEN** у колонки `event_kind.source` задан `check: [collector, manual]` без `nullable: false`, а строка не содержит `source`
- **THEN** нарушения `check_violated` нет

#### Scenario: Значение не того типа
- **WHEN** у колонки `task_priority.level` типа `integer` задан `check: [1, 2]`, а строка содержит `level: "1"`
- **THEN** `forge validate-seed` сообщает нарушение `invalid_value` и не сообщает `check_violated`

### Requirement: Значение колонки с генерацией задаётся в seed явно
Колонка с `generated: identity` SHALL считаться в seed колонкой NOT NULL: каждая строка MUST
содержать её значение, иначе — нарушение `null_value`. Seed SHALL NOT полагаться на значение,
которое выдаёт БД.

#### Scenario: Нет значения ключа с генерацией
- **WHEN** ключ таблицы `category` — `[id]` с `generated: identity`, а строка `tables[0].rows[0]` не содержит `id`
- **THEN** `forge validate-seed` сообщает нарушение `null_value` с путём `tables[0].rows[0].id`

#### Scenario: Явное значение ключа с генерацией
- **WHEN** ключ таблицы `category` — `[id]` с `generated: identity`, а все строки содержат `id`
- **THEN** seed корректен
