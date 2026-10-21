# Proposal

## Why

`forge close` принимает модель и changelog в каталог `db/` корня проекта, и этот путь зашит в код.
В репозитории разработки Liquibase Forge ручные проверочные прогоны `/forge` поэтому принимались
в отслеживаемый git `db/`: тестовые таблицы `customer`, `project` и `developer` попали в индекс,
а при поставке стали бы принятым состоянием целевого проекта. В целевом проекте `db/` должен
коммититься, а в репозитории разработки — отсутствовать.

## What Changes

- Корень принятого состояния задаётся переменной окружения `FORGE_ACCEPTED_DIR`: относительный
  путь внутри корня проекта, умолчание `db` при незаданной или пустой переменной.
- `forge close`, `forge report` и запасной путь `forge rollback` берут корень из настройки
  вместо литералов `Path("db")` и `db/changelog/master.yaml`.
- У `forge generate` аргумент `--accepted` становится необязательным: по умолчанию
  `<корень>/model.yaml`. Шаблон `forge-apply` больше не передаёт литерал `--accepted db/model.yaml`.
- `logicalFilePath` changeset остаётся `db/changelog/<штамп>.yaml` независимо от физического
  корня: журнал `databasechangelog` одинаков в разработке и в поставке.
- `forge status` получает проверку среды `accepted`, называющую итоговый корень. Корректное
  значение проверку проходит всегда; абсолютный путь или выход за корень проекта — непройденная
  проверка и код `2`.
- `.env.example` содержит `FORGE_ACCEPTED_DIR=db`, `make forge-env-sync` доставляет её в `.env`.
  В `.env` репозитория разработки задаётся `.forge/db`.
- `.gitignore` репозитория разработки получает `/db/` как страховку от незаданной переменной.
  Каталог `db/` в репозитории разработки отсутствует, без `.gitkeep`.
- Документация `docs/operation.md`, `docs/architecture.md`, `docs/domain.md` и `README.md`
  синхронизируется: корень принятого состояния вместо безусловного `db/`.

## Capabilities

### New Capabilities

Нет.

### Modified Capabilities

- `forge-operation-commands`: закрытие и отчёт работают с корнем принятого состояния из
  `FORGE_ACCEPTED_DIR`; статус проверяет и называет этот корень.
- `forge-migration`: `--accepted` необязателен и по умолчанию берётся из корня; запасной путь
  отката накатывает `master.yaml` из корня; `logicalFilePath` не зависит от физического корня.
- `forge-operation`: закрытие операции принимает модель в корень принятого состояния, а не
  в безусловный `db/`.
- `forge-environment`: шаблон окружения содержит `FORGE_ACCEPTED_DIR`, а репозиторий разработки
  исключает `db/` из git.

## Impact

- Код: `src/forge/cli/commands/close.py`, `report.py`, `generate.py`, `rollback.py`, `status.py`;
  `src/forge/operation/infrastructure/accepted_state.py`, `environment_probe.py`;
  `src/forge/migration/application/rollback_attempt/use_case.py`;
  `src/forge/shared/infrastructure/settings.py`.
- Шаблон беклога: `templates/forge-apply.md` — новая версия шаблона.
- Окружение: `.env.example`, `.gitignore`; `.env` репозитория разработки правится владельцем.
- Тесты: модульные тесты настройки, `close`, `report`, `generate`, `rollback`, `status`.
- Совместимость: при незаданной переменной поведение прежнее — корень `db`. Целевые проекты
  без `FORGE_ACCEPTED_DIR` работают без изменений.
- Ограничение поставки: `.gitignore` и `db/` репозитория разработки в поставку forge не входят.
  Механизм поставки forge в этот change не входит.
