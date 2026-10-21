# Design

## Context

Мотивация — в [proposal.md](./proposal.md#why). Решения ниже согласованы с владельцем
по итогам аудита навыком `project-docs` и прожарки.

Найдено при планировании:

- Текущий `README.md` состоит из разделов «Назначение», «Требования хоста», «Подготовка окружения»,
  «Подключение к БД с хоста», «Использование», «Проверки проекта», «Отличия от поставки kit'а».
  `CONTRIBUTING.md` и документа кейсов нет.
- Версия проекта `0.1.0` — поле `project.version` в `pyproject.toml`; лицензия — MIT (`LICENSE`);
  репозиторий `github.com/united-software-platform/liquibase-forge` публичный.
- `docs/operation.md` уже содержит таблицу команд с исходами по кодам `0`, `1`, `2` (раздел «Команды»)
  и код `2` для недопустимого `FORGE_ACCEPTED_DIR` (раздел «Принятое состояние»), а также порядок
  продолжения открытой операции, в том числе `forge resume` при статусе `stopped` (раздел «Навык forge»).
- Входящая ссылка на `README.md` есть одна: `docs/architecture.md`, строка 210, — «подготовка
  окружения и отличия от поставки kit'а описаны в README.md».
- Образцы навыка — `.claude/skills/project-docs/templates/{readme,contributing,use-cases}.md`.

## Goals / Non-Goals

**Goals:**

- Повторный аудит навыком `project-docs` не находит расхождений по `DGN-001`..`DGN-012`
  в `README.md`, `CONTRIBUTING.md` и `docs/use-cases.md`.
- Ни один факт текущего `README.md` не теряется: каждый либо остаётся, либо переносится в документ
  своего читателя, либо заменяется ссылкой на документ, где он уже изложен.

**Non-Goals:**

- Правка `docs/operation.md`, `docs/migration.md`, `docs/reconciliation.md`, `docs/model-format.md`,
  `docs/domain.md` и содержания `docs/architecture.md` — норма их не покрывает.
- Установщик Liquibase Forge — шаг 1 описывает ручное копирование.
- Бейджи сверх обязательного минимума.

## Decisions

### Читатели и документы

| Документ | Читатель | Голос |
|----------|----------|-------|
| `README.md` | Владелец целевого проекта, применяющий forge через агента | «вы» |
| `docs/use-cases.md` | Он же — за пределами основного пути | «я» |
| `CONTRIBUTING.md` | Правящий Liquibase Forge | безлично |

Путь документа кейсов — `docs/use-cases.md`, как в kit'е.

### Каркас `README.md`

1. Блок бейджей:
   - версия — `https://img.shields.io/badge/dynamic/toml` с `url` на `raw.githubusercontent.com`
     `pyproject.toml` ветки `main` и `query=$.project.version`, ссылка — `./pyproject.toml`;
   - лицензия — статический `license-MIT`, ссылка — `./LICENSE`.
1. Назначение:
   > Liquibase Forge строит модель данных PostgreSQL по намерению, сформулированному агенту,
   > проверяет её накатом, сверкой и откатом и принимает в `db/` вашего проекта. Здесь — путь
   > от установки до первой принятой модели; другие задачи — в документе кейсов, правка самого
   > forge — в `CONTRIBUTING.md`.
1. «Что нужно»: SDD Developer Kit с запущенным host-runner — ссылка на `tools/host-runner/README.md`,
   где описаны запуск и перезапуск после смены `AGENT_RUNNER_*`; Docker Compose 2.20+ — `include:`
   в `docker-compose.yml`; `python3` без сторонних пакетов; сеть при первой сборке образа.
1. «Шаг 1. Установить Liquibase Forge» — скопировать в целевой проект `src/forge/`, `pyproject.toml`,
   `uv.lock`, `tools/liquibase/`, `tools/forge-env/`, `docker/lbfr/`, `.claude/skills/forge/`
   и перенести проектные отличия четырёх файлов kit'а по таблице `CONTRIBUTING.md`;
   `.gitignore`, `db/`, `backlog/` не копируются.
1. «Шаг 2. Подготовить окружение» — агент выполняет `make forge-env-sync`, `make forge-env-check`,
   `make forge-env-up`; описания целей — по `make help`, без таблицы (`DGN-011`). Блок `Важно`
   о перезапуске сессии агента после правки `.env`. «Подробнее — кейс 2».
1. «Шаг 3. Подключить плагин `backlog@formular`» — `claude plugin marketplace add united-software-platform/formular`, затем `claude plugin install backlog@formular`,
   перезапуск сессии.
1. «Шаг 4. Построить модель» — `/forge <намерение>`, абзац о режимах `interactive` и `auto`,
   результат в корне принятого состояния. «Подробнее — кейс 3».
1. «Шаг 5. Закоммитить результат» — файлы и каталоги из `commit.files`, не `git add -A`;
   блок `Внимание` о строке `backlog/*` в `.gitignore`.
1. «Куда дальше» — `docs/use-cases.md`, справочник команд и кодов возврата `docs/operation.md`,
   `docs/migration.md`, `docs/reconciliation.md`, `docs/model-format.md`, `make help`,
   `CONTRIBUTING.md`.
1. «Ограничения» — установщика нет; Liquibase 5.x под лицензией FSL; корень следа — только
   `backlog/`, `BACKLOG_ROOT` не поддерживается.
1. «Лицензия» — MIT.

Таблицы версий в `README.md` нет — исключение `DOC-022`.

### Коды возврата — ссылкой на `docs/operation.md`

`DGN-012` в `README.md` закрывается переносом: фраза о коде `2` уходит в кейс 4 ссылкой
на раздел «Принятое состояние» `docs/operation.md`, а «Куда дальше» называет раздел «Команды»
как справочник кодов. Альтернатива — таблица «Код / Что значит / Что делаю» в `README.md` —
отвергнута: она продублировала бы `docs/operation.md`, где коды уже описаны.

### Состав `docs/use-cases.md`

| Кейс | Источник материала | Метки сверх тройки |
|------|-------------------|--------------------|
| 1. Хочу посмотреть построенную схему клиентом с хоста | «Подключение к БД с хоста»: `FORGE_DB_HOST_PORT`, `psql`, отличие от `FORGE_DB_PORT` | «Если порт открыт наружу» — учётные данные, обход `ufw` |
| 2. Хочу поднять окружение, а хостовый порт занят | `port is already allocated`, проверка `ss`, `DOCK-008` ссылкой | «Если не вышло» |
| 3. Хочу продолжить остановленную операцию | `docs/operation.md`, «Навык forge»: `/forge` подхватывает открытую операцию, `forge resume` при `stopped` | — |
| 4. Хочу перенести корень принятого состояния | `FORGE_ACCEPTED_DIR`, ручной перенос, проверка `accepted`, код `2` ссылкой | «Если не вышло» |
| 5. Хочу разрешить накат на другую БД | `FORGE_TEST_DB_ALLOWLIST`: формат, `*`, пустой перечень | «Если не вышло» |
| 6. Хочу сменить версию Liquibase или драйвера PostgreSQL | `LBFR_LIQUIBASE_BASE_IMAGE`, `LBFR_LIQUIBASE_POSTGRESQL_DRIVER`, смена `LBFR_LIQUIBASE_IMAGE` | «Если не вышло» |

«Если не вышло» в кейсах 4, 5, 6 — перезапуск сессии агента после правки `.env`. В кейсе 2 метка
называет `make forge-env-sync` при отсутствии `FORGE_DB_HOST_PORT`: хостовый порт агент не использует —
к БД он ходит по `FORGE_DB_PORT`, — и перезапуск сессии там ничего не меняет. В кейсе 4 коды
`forge status --latest` сведены в таблицу по `DGN-012`.

### Состав `CONTRIBUTING.md`

1. «Устройство репозитория» — таблицы «Код» и «Документы и носители значений»: `src/forge/`,
   `tools/liquibase/`, `tools/forge-env/`, `docker/lbfr/`, `tests/`, `openspec/`; `docs/architecture.md`,
   `docs/domain.md`, `pyproject.toml` как носитель версии, `LICENSE`, `docs/use-cases.md`, `rules/`;
   строка о рабочем пространстве USP и группе `toolkit`.
1. «Репозиторий разработки» — `FORGE_ACCEPTED_DIR=.forge/db` вручную в `.env`, исключения `.forge/`
   и `/db/` в `.gitignore`, почему `.gitignore`, `db/` и `backlog/` не входят в поставку forge.
1. «Отличия от поставки kit'а» — таблица четырёх файлов из `README.md`; перенос правок при обновлении
   kit'а — по `design.md` изменения `update-sdd-kit` словами и спецификации
   `openspec/specs/sdd-kit-delivery/spec.md` ссылкой; перезапуск раннера после правки белого списка.
1. «Блок бейджей» — карта «Бейдж / Источник значения / Режим / Цель ссылки» и ограничения блока.
1. «Проверки» — `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`,
   `sh tools/make-lint/check.sh` с комментариями; маркер `integration` и его пропуск.
1. «Правила и процесс» — таблица «Вопрос / Норма» кодами со ссылками; изменения ведутся через
   OpenSpec `/opsx:*`.

### Порождение из образцов

По разделу «Порождение из образца» навыка: блоки `> **Образец:** …` снимаются; ссылки
пересчитываются от расположения документа — для `docs/use-cases.md` на `../README.md`,
`../CONTRIBUTING.md`, `../rules/…`; у `CONTRIBUTING.md` и `docs/use-cases.md` таблица версий
образца заменяется записью `1.0.0` с задачей `OpenSpec change align-project-docs`.

### Входящая ссылка из `docs/architecture.md`

Строка 210 переводится на оба адреса: подготовка окружения — `README.md`, отличия от поставки
kit'а — `CONTRIBUTING.md`. Это единственная правка `docs/`, вне нормы `DGN-*`: без неё ссылка вела бы
не туда — `DOC-023`. В таблицу версий `docs/architecture.md` дописывается строка по `DOC-022`.

## Risks / Trade-offs

- [Бейдж версии читает `pyproject.toml` ветки `main`, а работа идёт в `forge-operation`] → до слияния
  бейдж показывает версию `main`; ограничение названо в карте бейджей `CONTRIBUTING.md`.
- [Перенос теряет факт текущего `README.md`] → задача сверки: каждый абзац старого `README.md`
  сопоставляется с местом в новых документах.
- [Шаг 1 описывает ручное копирование, которое может расходиться с реальным составом] → состав
  перечислен путями, существующими в репозитории; отсутствие установщика названо в «Ограничениях».
- [Нормы проверяются только чтением — машинной проверки `DGN-*` нет] → повторный аудит навыком
  `project-docs` по каждому правилу и каждому документу.

## Migration Plan

Откат до коммита — удаление `CONTRIBUTING.md` и `docs/use-cases.md` и возврат `README.md`
и строки `docs/architecture.md` к закоммиченному состоянию по явному указанию владельца (`GIT-018`).
