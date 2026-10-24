## ADDED Requirements

### Requirement: Изменения модели не ломают принятый seed
`forge generate` MUST проверять модель попытки против принятого seed и при конфликте возвращать
`1` с `changelog: null` и перечнем `seed_conflict`. Конфликты:
- удаление таблицы принятого seed;
- новая колонка NOT NULL в таблице с seed-строками;
- новый FK или набор `unique`, которому строки принятого seed не отвечают.

Нет `<корень>/seed.yaml` — конфликтов нет.

#### Scenario: Удаление справочника
- **WHEN** модель попытки удаляет таблицу `order_status`, а она есть в принятом seed
- **THEN** команда возвращает `1`, `seed_conflict` называет `order_status` и вид `seeded_table_dropped`

#### Scenario: Новая обязательная колонка
- **WHEN** модель попытки добавляет колонку `sort_order` с `nullable: false` в `order_status`, у которой в принятом seed есть строки
- **THEN** команда возвращает `1`, `seed_conflict` называет колонку и вид `not_null_column_added`

#### Scenario: Обязательная колонка в пустом справочнике
- **WHEN** таблица есть в принятом seed с `rows: []`, а модель добавляет в неё колонку NOT NULL
- **THEN** конфликта нет

#### Scenario: Новый unique, которому seed не отвечает
- **WHEN** модель попытки добавляет набор `unique` `[title]`, а две строки принятого seed имеют одинаковый `title`
- **THEN** команда возвращает `1`, `seed_conflict` называет набор и вид `unique_violated_by_seed`

#### Scenario: Удаление колонки справочника
- **WHEN** модель попытки удаляет колонку `order_status.color`
- **THEN** конфликта нет, changelog строится как обычно
