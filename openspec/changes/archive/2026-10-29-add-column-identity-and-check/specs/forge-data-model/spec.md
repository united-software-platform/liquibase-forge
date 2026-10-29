# Spec Delta

## MODIFIED Requirements

### Requirement: Колонка задаётся именем, типом и допустимостью NULL
Каждый элемент `columns` MUST быть отображением с полями `name` и `type` и MAY содержать `nullable`,
параметры своего типа, `generated` и `check`. Значение `nullable` MUST быть логическим; без него
колонка SHALL допускать NULL.

#### Scenario: Колонка без nullable
- **WHEN** колонка `email` типа `text` вне первичного ключа не содержит `nullable`
- **THEN** модель корректна, и колонка допускает NULL

#### Scenario: nullable не логическое
- **WHEN** у колонки `tables[0].columns[2]` задано `nullable: "no"`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[2].nullable`

#### Scenario: Колонка без generated и check
- **WHEN** ни одна колонка модели не содержит `generated` и `check`
- **THEN** модель корректна, как и до введения этих полей

## ADDED Requirements

### Requirement: Генерация значения колонки задаётся полем generated
Поле `generated` MUST быть строкой `identity`: значение колонки выдаёт БД, а явное значение
при вставке допускается. Другая строка SHALL быть нарушением `unknown_generation` с путём поля,
значение не строкой — нарушением вида значения.

#### Scenario: Ключ с генерацией значения
- **WHEN** колонка `id` типа `bigint` входит в `primary_key` и имеет `generated: identity`
- **THEN** модель корректна

#### Scenario: Генерация вне первичного ключа
- **WHEN** колонка `seq_no` типа `integer` вне первичного ключа имеет `generated: identity` и `nullable: false`
- **THEN** модель корректна

#### Scenario: Неизвестный способ генерации
- **WHEN** у колонки `tables[0].columns[0]` задано `generated: sequence`
- **THEN** `forge validate` сообщает нарушение `unknown_generation` с путём `tables[0].columns[0].generated`

#### Scenario: Логическое значение вместо строки
- **WHEN** у колонки `tables[0].columns[0]` задано `generated: true`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[0].generated`

### Requirement: Генерация значения допустима только у целой колонки NOT NULL
Колонка с `generated` MUST иметь тип `integer` или `bigint`, иначе — нарушение
`generated_requires_integer` с путём `generated`. Такая колонка SHALL быть NOT NULL: явное
`nullable: true` MUST давать нарушение `generated_nullable` с путём `nullable`. Без `nullable`
колонка с `generated` SHALL считаться NOT NULL.

#### Scenario: Генерация у строковой колонки
- **WHEN** колонка `tables[0].columns[0]` типа `uuid` имеет `generated: identity`
- **THEN** `forge validate` сообщает нарушение `generated_requires_integer` с путём `tables[0].columns[0].generated`

#### Scenario: Генерация у колонки, допускающей NULL
- **WHEN** колонка `tables[0].columns[1]` типа `bigint` имеет `generated: identity` и `nullable: true`
- **THEN** `forge validate` сообщает нарушение `generated_nullable` с путём `tables[0].columns[1].nullable`

#### Scenario: Генерация без nullable вне ключа
- **WHEN** колонка `seq_no` типа `integer` вне первичного ключа имеет `generated: identity` и не содержит `nullable`
- **THEN** модель корректна, и колонка считается NOT NULL

### Requirement: В таблице не больше одной колонки с генерацией значения
Таблица MUST содержать не больше одной колонки с `generated`. Вторая и каждая следующая такая
колонка SHALL давать нарушение `duplicate_generated` с путём её поля `generated`.

#### Scenario: Две колонки с генерацией
- **WHEN** в таблице `tables[0]` колонки `columns[0]` и `columns[2]` обе имеют `generated: identity`
- **THEN** `forge validate` сообщает нарушение `duplicate_generated` с путём `tables[0].columns[2].generated`

### Requirement: Перечень значений колонки задаётся полем check
Поле `check` MUST быть непустым списком значений без повторов: значение колонки, отличное
от NULL, SHALL входить в перечень. Пустой список MUST давать нарушение `check_empty` с путём
`check`, повтор — `check_duplicate_value` с путём повторного элемента. Значение `check`
не списком SHALL быть нарушением вида значения.

#### Scenario: Колонка с перечнем
- **WHEN** колонка `source` типа `string` с `length: 16` имеет `check: [collector, manual]`
- **THEN** модель корректна

#### Scenario: Пустой перечень
- **WHEN** у колонки `tables[0].columns[3]` задано `check: []`
- **THEN** `forge validate` сообщает нарушение `check_empty` с путём `tables[0].columns[3].check`

#### Scenario: Повтор значения
- **WHEN** у колонки `tables[0].columns[3]` задано `check: [manual, collector, manual]`
- **THEN** `forge validate` сообщает нарушение `check_duplicate_value` с путём `tables[0].columns[3].check[2]`

#### Scenario: Перечень строкой
- **WHEN** у колонки `tables[0].columns[3]` задано `check: manual`
- **THEN** `forge validate` сообщает нарушение с путём `tables[0].columns[3].check`

#### Scenario: NULL в колонке с перечнем
- **WHEN** колонка `source` вне первичного ключа имеет `check: [collector, manual]` и не содержит `nullable`
- **THEN** модель корректна, и колонка допускает NULL

### Requirement: Перечень допустим у строковых и целых колонок
Поле `check` MUST использоваться только у колонок типов `string`, `text`, `integer` и `bigint`,
иначе — нарушение `check_unsupported_type` с путём `check`. Колонка SHALL NOT иметь одновременно
`check` и `generated`: такое сочетание MUST давать нарушение `check_with_generated` с путём `check`.

#### Scenario: Перечень у логической колонки
- **WHEN** колонка `tables[0].columns[2]` типа `boolean` имеет `check: [true]`
- **THEN** `forge validate` сообщает нарушение `check_unsupported_type` с путём `tables[0].columns[2].check`

#### Scenario: Перечень вместе с генерацией
- **WHEN** колонка `tables[0].columns[0]` типа `integer` имеет `generated: identity` и `check: [1, 2]`
- **THEN** `forge validate` сообщает нарушение `check_with_generated` с путём `tables[0].columns[0].check`

### Requirement: Значения перечня соответствуют типу колонки
Значение перечня колонки `string` или `text` MUST быть строкой YAML, а у `string` его длина
в символах MUST NOT превышать `length`. Значение колонки `integer` или `bigint` MUST быть целым
числом YAML в пределах типа. Значение не того вида SHALL давать `check_value_wrong_kind`, выход
за длину или диапазон — `check_value_out_of_range`, с путём элемента.

#### Scenario: Число в перечне строковой колонки
- **WHEN** колонка типа `text` имеет `check: [manual, 404]`
- **THEN** `forge validate` сообщает нарушение `check_value_wrong_kind` с путём `tables[0].columns[1].check[1]`

#### Scenario: Значение длиннее length
- **WHEN** колонка типа `string` с `length: 6` имеет `check: [manual, collector]`
- **THEN** `forge validate` сообщает нарушение `check_value_out_of_range` с путём `tables[0].columns[1].check[1]`

#### Scenario: Строка в перечне целой колонки
- **WHEN** колонка типа `integer` имеет `check: [1, "2"]`
- **THEN** `forge validate` сообщает нарушение `check_value_wrong_kind` с путём `tables[0].columns[1].check[1]`

#### Scenario: Выход за диапазон integer
- **WHEN** колонка типа `integer` имеет `check: [1, 3000000000]`
- **THEN** `forge validate` сообщает нарушение `check_value_out_of_range` с путём `tables[0].columns[1].check[1]`
