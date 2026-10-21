# Tasks

## 1. Путь к принятому master в сценарии отката

- [x] 1.1 Перед правкой пройти гейт GIT-020 для `src/forge/migration/application/rollback_attempt/use_case.py`, `src/forge/cli/commands/rollback.py`, `tests/migration/application/test_rollback_attempt.py`, `tests/integration/test_migration_rollback.py`; проверка — `git status --` и `git diff --` по каждому пути пусты либо незакоммиченные правки зафиксированы с подтверждённым кодом задачи
- [x] 1.2 Добавить в `tests/migration/application/test_rollback_attempt.py` регрессионный тест по design.md: запасной путь сценария, собранного с `accepted_master="trail/accepted/master.yaml"` и `FakeDatabase(master_exists=True)`, даёт `db.calls == ["recreate", "update trail/accepted/master.yaml"]`; проверка — тест падает до правки сценария (неизвестный аргумент конструктора)
- [x] 1.3 В `RollbackAttemptUseCase` принять `accepted_master: str = ACCEPTED_MASTER` в конструкторе и использовать сохранённое значение во всех местах `_recreate` (проверка наличия, накат, детали `accepted_restored`); обновить docstring класса; проверка — `uv run pytest tests/migration/application/test_rollback_attempt.py` зелёный, включая новый тест
- [x] 1.4 В `src/forge/cli/commands/rollback.py` дать `build_use_case` параметр `accepted_master: str = ACCEPTED_MASTER` и передать его в конструктор; аргументы, вывод и коды `forge rollback` не менять; проверка — `uv run pytest tests/cli/test_rollback.py` зелёный

## 2. Изоляция интеграционных тестов отката

- [x] 2.1 В `tests/integration/test_migration_rollback.py` перевести хелпер `_rollback` на `rollback.run(Namespace(operation=..., attempt=1), build_use_case(accepted_master=str(trail / "accepted" / "master.yaml")))` с чтением JSON из `capsys`, как в `forge()`; проверка — `uv run pytest -m integration tests/integration/test_migration_rollback.py` зелёный, в том числе `test_foreign_entry_after_attempt_recreates_database`
- [x] 2.2 Исправить ошибки mypy, существовавшие до change, в `tests/integration/test_reconciliation_cycle.py`: аннотацию предмета расхождения в `DRIFTS` и в параметре `subject` расширить до `tuple[str | None, str | None, str | None]` — у случаев `changeset_not_executed` таблица равна `None`; перед правкой пройти гейт GIT-020 для файла; проверка — `uv run mypy src tests` без ошибок, `uv run pytest -m integration tests/integration/test_reconciliation_cycle.py` зелёный

## 3. Интеграционная проверка

- [x] 3.1 Прогнать линтеры и полный набор тестов; проверка — `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src tests` без ошибок, `uv run pytest` и `uv run pytest -m integration` зелёные, пропусков по причине окружения нет

## Workflow follow-up

- Коммит — только по явному запросу пользователя, с кодом задачи по GIT-009/GIT-010.
- После зелёного полного прогона закрыть задачу 4.3 change `publish-db-port`.
- Архивировать изменение после ревью.
