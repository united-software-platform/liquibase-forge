# Proposal

## Why

Интеграционный тест `tests/integration/test_migration_rollback.py::test_foreign_entry_after_attempt_recreates_database`
стабильно падает: `forge rollback` возвращает `verified = False` и код `1`. На запасном пути
`recreate_database` сценарий отката накатывает принятый changelog по пути из константы модуля
`ACCEPTED_MASTER = "db/changelog/master.yaml"`, а фикстура `trail` переводит рабочий каталог в корень
проекта. В тестовую БД попадает настоящее принятое состояние проекта: `db/changelog/20261018-235648.yaml`
создаёт таблицу `customer`, которая есть и в модели-примере теста, и проверка `table_absent`
ложно падает.

Тест опирается на состояние `db/` репозитория: он прошёл, пока принятых операций не было, и сломался
после первой принятой операции forge. Любая следующая принятая операция может сломать его снова.
Поведение продукта при этом корректно: в реальной операции попытка строится от того же принятого
состояния, и таблиц из него в changelog попытки не бывает.

## What Changes

- Путь к принятому `master.yaml` становится параметром сценария отката `RollbackAttemptUseCase`
  вместо константы модуля; значение по умолчанию — `db/changelog/master.yaml`.
- Сборка сценария в `forge rollback` передаёт значение по умолчанию; аргументы, вывод и коды
  возврата команды не меняются.
- Интеграционные тесты отката передают путь внутри своего каталога trail, где файла нет: запасной
  путь пересоздаёт БД пустой, как и ожидает тест.
- Добавляется модульный регрессионный тест: запасной путь проверяет наличие и накатывает именно
  переданный путь.

## Capabilities

### New Capabilities

Нет.

### Modified Capabilities

Нет: требования `forge-migration` к запасному пути («Запасной путь пересоздаёт тестовую БД»)
не меняются — команда по-прежнему накатывает `db/changelog/master.yaml`, если он есть. Change
помечен `skip_specs: true`.

## Impact

- `src/forge/migration/application/rollback_attempt/use_case.py` — путь к принятому master
  передаётся в конструктор сценария.
- `src/forge/cli/commands/rollback.py` — `build_use_case` принимает путь с прежним значением
  по умолчанию.
- `tests/integration/test_migration_rollback.py` — откат вызывается через сценарий с путём
  внутри trail.
- `tests/migration/application/test_rollback_attempt.py` — регрессионный модульный тест.
- Внешние контракты (CLI `forge rollback`, `rollback.json`, навык `forge`) не затрагиваются.
- Задача 4.3 change `publish-db-port` (`uv run pytest -m integration`) зависит от этого
  исправления: без него полный прогон интеграционных тестов не зелёный.
