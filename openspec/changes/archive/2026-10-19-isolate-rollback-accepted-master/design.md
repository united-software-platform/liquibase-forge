# Design

## Context

- `RollbackAttemptUseCase` берёт путь к принятому changelog из константы модуля
  `ACCEPTED_MASTER = "db/changelog/master.yaml"` и использует его в `_recreate`: проверяет наличие
  через `ChangelogReaderInterface.exists`, накатывает через `LiquibaseGatewayInterface.update`
  и упоминает в деталях проверки `accepted_restored`.
- Путь относительный и разрешается от рабочего каталога процесса. Шлюз принимает changelog только
  из проекта, поэтому фикстура `trail` делает `chdir` в корень проекта и кладёт след операции
  в `.forge/test-trails/<uuid>/` — внутри проекта.
- `forge rollback` собирает сценарий в `build_use_case()`. Функция `run(args, use_case=None)` уже
  принимает готовый сценарий и вызывает `build_use_case()`, только если сценарий не передан.
- Интеграционные тесты вызывают CLI через `main(argv)` в том же процессе и читают JSON-вывод
  через `capsys`.
- Мотивация — см. proposal.md, раздел Why.

## Goals / Non-Goals

**Goals:**

- Интеграционные тесты отката не зависят от содержимого `db/` проекта.
- Значение по умолчанию и поведение `forge rollback` для пользователя и навыка `forge` прежние.

**Non-Goals:**

- Изоляция остальных команд forge (`generate`, `close`, `report`) от `db/` проекта: принятое
  состояние там уже передаётся аргументами либо проверяется на `tmp_path`.
- Изменение проверок возврата (`table_absent`, `column_absent`) с учётом принятого состояния:
  в реальной операции пересечения не бывает (см. proposal.md).

## Decisions

### Путь — параметр конструктора сценария

`RollbackAttemptUseCase(dependencies, accepted_master="db/changelog/master.yaml")`. Константа
модуля остаётся как значение по умолчанию; во всех трёх местах `_recreate` используется
сохранённое значение.

Рассмотренные альтернативы:

- Поле `RollbackDependencies` — отклонено: структура объединяет контракты окружения, строковый
  путь нарушил бы её смысл.
- Поле `RollbackAttemptInput` и ключ CLI `--accepted-master` — отклонено: меняет публичный контракт
  команды и требование спеки `forge-migration`, хотя пользователю ключ не нужен.
- Переменная окружения `FORGE_ACCEPTED_MASTER` — отклонено: добавляет настройку в `.env.example`,
  которую `make forge-env-sync` начал бы переносить в `.env` каждой установки.
- Подмена константы через `monkeypatch.setattr` в тесте — отклонено пользователем: тест остаётся
  привязан к внутреннему устройству модуля.

### `build_use_case` принимает путь с тем же значением по умолчанию

`build_use_case(accepted_master=ACCEPTED_MASTER)` передаёт значение в конструктор. Вызов из `run`
без аргументов сохраняет прежнее поведение.

### Интеграционный тест вызывает `run` с собранным сценарием

Хелпер `_rollback` в `tests/integration/test_migration_rollback.py` вызывает
`rollback.run(Namespace(operation=..., attempt=1), build_use_case(accepted_master=...))` и читает
JSON из `capsys`, как `forge()`. Путь — `<trail>/accepted/master.yaml`, файла по нему нет. Это
согласовано с построением попытки (`--accepted missing.yaml`) и с ожиданием пустой БД
(`_state(target) == ([], [])`). Хелпер общий для всех тестов отката в файле: остальные сценарии
до запасного пути не доходят, но изоляция не должна зависеть от выбранного пути.

Пропускается только разбор аргументов `argparse`: обработка исключений, JSON-вывод и код возврата
идут через тот же `run`, что и в CLI.

### Регрессионный модульный тест

В `tests/migration/application/test_rollback_attempt.py` запасной путь со сценарием, собранным
с нестандартным путём, вызывает шлюз с этим путём: `db.calls` содержит `update <путь>`. До правки
тест падает на неизвестном аргументе конструктора.

## Risks / Trade-offs

- [Интеграционный тест запасного пути больше не накатывает настоящий принятый master] → накат
  принятого `master.yaml` через шлюз проверяет `tests/integration/test_accepted_master.py`,
  а ветку «master есть — накатить» — модульный `test_foreign_entry_after_attempt_takes_fallback`.
- [Интеграционный тест обходит `argparse`] → разбор аргументов `forge rollback` покрыт тестами
  `tests/cli/test_rollback.py`.
- [Подставная `FakeDatabase.exists` не смотрит на путь] → регрессионный тест проверяет путь
  по вызову шлюза (`update <путь>`), а не по `exists`.

## Migration Plan

Миграция не нужна: значение по умолчанию прежнее, внешние контракты не меняются. Откат — вернуть
константу в `_recreate` и прежний хелпер теста.
