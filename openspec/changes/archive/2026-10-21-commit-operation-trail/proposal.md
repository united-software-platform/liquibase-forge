# Proposal

## Why

В целевом проекте принятое состояние коммитится, но след операции, из которого оно получено, —
беклог операции, беклоги попыток, `reconcile.json`, `rollback.json` — `forge report` для коммита
не называет. Владелец коммитит модель без объяснения, как она получена, а после операции
`failure` не коммитит ничего. Кроме того, файлы обмена со шлюзом в `.forge/` скрыты только
`.gitignore` репозитория разработки, который в поставку не входит: в целевом проекте они
попадают в `git status`.

## What Changes

- `forge report` при закрытой операции (`success` и `failure`) перечисляет в `commit.files`
  каталог операции `<корень следа>/forge-model/<штамп>/` и каталог беклога каждой начатой
  попытки `<корень следа>/forge-apply/<штамп>-<N>/`; при `success` — вместе с файлами корня
  принятого состояния. Для открытой операции `commit` остаётся `null`.
- Навык `forge` на последнем шаге называет владельцу файлы для коммита из отчёта при `success`
  и при `failure`; описание навыка называет корень принятого состояния вместо `db/`.
- `forge` при записи файла запроса и шлюз Liquibase при записи файла результата кладут в `.forge/`
  `.gitignore` со строкой `*`, если его там нет. Файлы обмена скрыты от git в любом проекте без правки `.gitignore` проекта.
- В репозитории разработки след остаётся под `backlog/*` в `.gitignore` — поведение не меняется
  и фиксируется требованием.
- `docs/operation.md` фиксирует ограничение: корень следа forge — `backlog/`, переопределение
  `BACKLOG_ROOT` для операций forge не поддерживается, потому что шаблоны называют пути следа
  литералами.
- Документация раскладки следа (`docs/architecture.md`, `docs/operation.md`, `README.md`)
  различает целевой проект, где след коммитится, и репозиторий разработки, где нет.

## Capabilities

### New Capabilities

Нет.

### Modified Capabilities

- `forge-operation-commands`: отчёт перечисляет для коммита след закрытой операции, а не только
  принятые файлы при `success`.
- `forge-operation`: навык называет владельцу файлы для коммита при `success` и `failure`.
- `forge-liquibase-gateway`: каталог обмена `.forge/` скрывает своё содержимое от git.
- `forge-environment`: репозиторий разработки не хранит след операций в git.

## Impact

- Код: `src/forge/operation/application/build_report/` (перечень файлов следа),
  `src/forge/cli/commands/report.py`, `src/forge/migration/infrastructure/runner_gateway.py`,
  `tools/liquibase/gateway.py`.
- Навык: `.claude/skills/forge/SKILL.md`.
- Документация: `docs/operation.md`, `docs/architecture.md`, `README.md`.
- Тесты: `tests/cli/test_report.py`, тесты сценария отчёта, `tests/migration/infrastructure/test_runner_gateway.py`,
  `tests/tools/test_liquibase_gateway.py`.
- Совместимость: поле `commit` отчёта при `failure` становится непустым — потребитель отчёта,
  проверявший `commit is None` как признак неудачи, должен смотреть на `operation.status`.
- Каталог `.forge/` в репозитории разработки получает `.gitignore`; строка `.forge/` в корневом
  `.gitignore` остаётся.
