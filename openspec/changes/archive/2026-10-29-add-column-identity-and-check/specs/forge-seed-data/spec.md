# Spec Delta

## ADDED Requirements

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
