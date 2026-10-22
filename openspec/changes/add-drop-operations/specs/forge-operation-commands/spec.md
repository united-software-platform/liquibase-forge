# Spec Delta

## MODIFIED Requirements

### Requirement: Статус операции читается из её беклога
`forge status --operation <беклог операции>` MUST печатать намерение, режим, признак согласия
на удаления `allow_drop`, статус операции, вердикт, беклог и каталог каждой попытки и номер
подтверждённой попытки. Подтверждённой SHALL считаться попытка с вердиктом `success`. Беклог
без поля `allow_drop` MUST давать `allow_drop: false`.

#### Scenario: Операция после первой неудачи
- **WHEN** у операции `verdict.attempt_1: failure`, остальные вердикты пусты
- **THEN** ответ называет статус `running`, одну использованную попытку и отсутствие подтверждённой попытки

#### Scenario: Беклога нет
- **WHEN** путь `--operation` не ведёт к беклогу операции
- **THEN** команда возвращает код `2`

#### Scenario: Признак согласия на удаления
- **WHEN** беклог операции содержит `mode: auto` и `allow_drop: true`
- **THEN** ответ называет режим `auto` и `allow_drop: true`

#### Scenario: Беклог прежнего шаблона
- **WHEN** беклог операции не содержит поля `allow_drop`
- **THEN** ответ называет `allow_drop: false`

## ADDED Requirements

### Requirement: Отчёт перечисляет удаления итогового changelog
`forge report` MUST содержать `allow_drop` операции и перечень `destructive` — удаления
итогового changelog отчёта: принятого при `success`, иначе changelog последней начатой попытки.
Элемент перечня SHALL содержать таблицу и колонку; удалённая таблица MUST иметь `column: null`.
Нет итогового changelog или удалений в нём — перечень пуст.

#### Scenario: Успешная операция с удалениями
- **WHEN** операция закрыта со статусом `success`, а принятый changelog удаляет таблицу `invoice_line` и колонку `customer.email`
- **THEN** `destructive` содержит `{table: invoice_line, column: null}` и `{table: customer, column: email}`

#### Scenario: Операция без удалений
- **WHEN** итоговый changelog операции только создаёт таблицы
- **THEN** `destructive` — пустой перечень

#### Scenario: Попыток не было
- **WHEN** операция остановлена до первой попытки
- **THEN** `destructive` — пустой перечень
