## MODIFIED Requirements

### Requirement: Откат не трогает подтверждённую попытку
`forge rollback --operation <беклог операции> --attempt <N>` при вердикте `success` попытки N
MUST возвращать код `0`, не меняя БД и не записывая `rollback.json`. Единственное исключение —
откат при отказе от операции: команда `forge abandon` MUST откатывать и попытку с вердиктом
`success` тем же порядком, что неуспешную, с проверкой возврата и записью `rollback.json`.

#### Scenario: Откат после успешной сверки
- **WHEN** во фронтматтере беклога операции `verdict.attempt_1: success`
- **THEN** команда возвращает код `0`, схема и журнал Liquibase не изменились

#### Scenario: Откат подтверждённой попытки при отказе
- **WHEN** у незакрытой операции `verdict.attempt_1: success`, и от операции отказываются
- **THEN** changeset попытки сняты, проверка возврата пройдена, `rollback.json` попытки записан с вердиктом `success` и `verified: true`
