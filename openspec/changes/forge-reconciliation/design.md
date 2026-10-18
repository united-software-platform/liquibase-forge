# Design

## Context

Мотивация — в proposal.md, требования — в `specs/forge-reconciliation/spec.md`.

Исходное состояние:

- **Моделирование (change 1).** Даёт `DataModel` и сценарий `LoadModelUseCase`.
- **Миграция (change 2).** Пишет changelog: `id` вида `<штамп>-<NN>`, `author: forge`,
  `logicalFilePath` у каждого changeset. Накатывает его через шлюз и знает отображение типов
  модели в типы Liquibase.
- **Код тестовой среды живёт в модуле `migration`:**
  - `TargetDatabase`, `TestDatabaseAllowlist` и `parse_allowlist` — в домене;
  - `DatabaseCredentials`, `SettingsUnavailableError`, `DatabaseUnavailableError` —
    в приложении;
  - `EnvironmentSettings`, `PostgresConnector` и `JsonResultWriter` — в инфраструктуре.
- **Карта контекстов `domain.md`** прямо запрещает Сверке зависеть от Миграции: сверка читает
  фактическую схему из БД, а не из changelog.
- **Беклог попытки** вызывает `forge reconcile --model {{trail}}/model.yaml --changelog
  {{trail}}/changelog.yaml` и ждёт `{{trail}}/reconcile.json`; код `1` в нём — штатный исход.

## Goals / Non-Goals

**Goals:**

- Вердикт попытки, который опирается только на фактическое состояние БД и журнала.
- Расхождения, по которым агент без чтения БД понимает, что править в модели.
- Сверка и Миграция не знают друг о друге; общее у них — только ядро тестовой среды.

**Non-Goals:**

- Сверка представлений, последовательностей, индексов, внешних ключей, ограничений
  уникальности и проверок: в первом срезе модели их нет. Лишняя таблица видна, лишний индекс — нет.
- Сверка схем, кроме `public`.
- Запись вердикта во фронтматтер беклога — это делает агент по шаблону; статусы операции —
  change 4.

## Decisions

### Общее ядро `forge.shared`

Компоненты тестовой среды переносятся из `migration` в новый пакет `src/forge/shared/` с теми же
слоями:

| Слой | Компоненты |
|------|------------|
| Домен | `TargetDatabase`, `AllowedDatabase`, `TestDatabaseAllowlist`, `parse_allowlist`, `DatabaseNotAllowedError`, `InvalidAllowlistError` |
| Приложение | `DatabaseCredentials`, `TargetDatabaseSettingsInterface`, `SettingsUnavailableError`, `DatabaseUnavailableError`, `ResultWriterInterface` |
| Инфраструктура | `EnvironmentSettings` (`FORGE_DB_*`, `FORGE_TEST_DB_ALLOWLIST`), `PostgresConnector`, `JsonResultWriter` |

- **Что остаётся в Миграции.** Настройки раннера (`AGENT_RUNNER_*`) — отдельной функцией
  `runner_settings(env)` в `migration/infrastructure`: ими пользуется только шлюз Liquibase.
  Пересоздание БД со служебной БД `postgres` тоже остаётся в Миграции.
- **Перенос без обратной совместимости.** Импорты в `migration`, `cli` и тестах правятся,
  старых модулей-переходников не остаётся. Тесты переносимых компонентов переезжают
  в `tests/shared/`.
- **Почему общее ядро, а не дубли.** Альтернатива — дублировать адрес, перечень и подключение
  в Сверке. Отклонена: правила перечня тестовых БД должны быть одними на все команды,
  а change 4 (`forge status`) нужен тот же набор третий раз.

Общее ядро (Shared Kernel) — штатная связь контекстов по DDD. Ограничение: в него попадает
только то, что одинаково значит для всех контекстов, — среда исполнения, а не предметные понятия.

### Описание типа колонки

`ColumnType` в Моделировании получает `__str__`: `string(255)`, `decimal(12, 2)`, `uuid`. Так
тип показывают и неаддитивные изменения Миграции, и расхождения Сверки. Функция `_type`
в `migration/domain/additive_diff.py` заменяется на `str(column_type)`.

### Состав модуля `reconciliation`

| Слой | Компонент | Роль |
|------|-----------|------|
| Домен | `ActualColumn`, `ActualTable`, `ActualSchema` | Фактическая схема: колонка — имя, тип модели либо `None` и исходное имя типа PostgreSQL, допустимость NULL; таблица — колонки и упорядоченный ключ либо `None` |
| Домен | `Discrepancy` | Расхождение: вид, таблица, колонка, `id` changeset, ожидаемое, фактическое, сообщение |
| Домен | `SchemaComparison` | Доменный сервис: `DataModel` против `ActualSchema` |
| Домен | `ExpectedChangeSet`, `JournalRecord`, `JournalCheck` | Changeset попытки, запись журнала и доменный сервис их сравнения |
| Приложение | `ReconcileUseCase` с `Input` и `Output` | Сценарий сверки |
| Приложение | `SchemaIntrospectorInterface`, `JournalRecordsReaderInterface`, `ChangesetListReaderInterface`, `ChangelogUnreadableError` | Контракты интроспекции, журнала и чтения changelog (CLAR-006) |
| Инфраструктура | `PsycopgSchemaIntrospector`, `PsycopgJournalRecordsReader`, `YamlChangesetListReader` | Реализации на `psycopg` и PyYAML |
| `cli` | `reconcile` | Разбор аргументов, сборка, JSON и код возврата |

Сверка читает changelog собственным разборщиком: ей нужны только `id`, `author`
и `logicalFilePath`. Разборщик Миграции она не импортирует (DDD-005).

### Фактическая схема и обратное отображение типов

`PsycopgSchemaIntrospector` читает каталог одним подключением:

- **Таблицы:** `pg_class` с `relkind IN ('r', 'p')` в схеме `public`, кроме `databasechangelog`
  и `databasechangeloglock`.
- **Колонки:** `pg_attribute` с `attnum > 0` и без удалённых, тип —
  `format_type(atttypid, atttypmod)`, NOT NULL — `attnotnull`.
- **Первичный ключ:** `pg_constraint` с `contype = 'p'`, колонки по `conkey WITH ORDINALITY`.

Обратное отображение типов — ACL (DDD-026). Тип PostgreSQL превращается в тип модели,
и домен сравнивает объекты-значения `ColumnType`, а не строки СУБД.

| `format_type` | Тип модели |
|---------------|------------|
| `integer`, `bigint`, `boolean`, `text`, `date`, `uuid` | одноимённый |
| `character varying(n)` | `string(n)` |
| `numeric(p,s)` | `decimal(p, s)` |
| `timestamp without time zone` | `timestamp` |
| `timestamp with time zone` | `timestamp_tz` |
| любой другой, включая `character varying` без длины и `numeric` без точности | `None`, исходная строка сохраняется для расхождения |

Прямое отображение (модель → Liquibase) живёт в Миграции. Согласованность двух отображений
проверяет интеграционный тест: changelog модели со всеми десятью типами накатывается и
сверяется без расхождений.

### Виды расхождений и порядок

| Вид | Таблица | Колонка | Ожидаемое | Фактическое |
|-----|---------|---------|-----------|-------------|
| `table_missing` | да | — | `present` | `absent` |
| `table_unexpected` | да | — | `absent` | `present` |
| `column_missing` | да | да | тип модели | `absent` |
| `column_unexpected` | да | да | `absent` | тип в БД |
| `column_type_mismatch` | да | да | тип модели | тип в БД либо исходный тип PostgreSQL |
| `column_nullable_mismatch` | да | да | `NULL` / `NOT NULL` | `NULL` / `NOT NULL` |
| `primary_key_mismatch` | да | — | `[a, b]` | `[b, a]` либо `absent` |
| `changeset_not_executed` | — | — | `EXECUTED` | `absent` либо значение `EXECTYPE` |

Для `changeset_not_executed` указывается `id` changeset.

Порядок устойчив и повторяет порядок модели:

1. Таблицы модели по порядку. Внутри таблицы: колонки модели по порядку (`column_missing`,
   `column_type_mismatch`, `column_nullable_mismatch`), затем лишние колонки по имени, затем
   первичный ключ. Отсутствующая таблица даёт одно расхождение без расхождений её колонок.
1. Лишние таблицы по имени.
1. Changeset в порядке changelog.

### Журнал Liquibase

`JournalCheck` для каждого `ExpectedChangeSet(id, author, filename)` ищет запись журнала
с тем же `id`, `author` и `filename`.

- **Записи нет** — `changeset_not_executed` с фактическим `absent`.
- **`EXECTYPE` не `EXECUTED`** — то же расхождение с фактическим значением.
- **Таблицы журнала нет** — записей ноль.

`filename` в changelog — `logicalFilePath` changeset, так совпадает и запись наката из следа,
и запись из `db/`.

### Команда `forge reconcile`

| Код | Когда | `reconcile.json` |
|-----|-------|------------------|
| `0` | Расхождений нет, вердикт `success` | Записан |
| `1` | Есть расхождения, вердикт `failure` | Записан |
| `2` | Не заданы переменные окружения, БД вне перечня тестовых, БД недоступна, модель не прочитать или она некорректна, changelog не прочитать | Не записан |

- **Перечень тестовых БД** проверяется до подключения: сверка тоже работает только с тестовой
  БД (BR-016). При коде `2` файла нет, иначе беклог счёл бы сверку выполненной.
- **`reconcile.json`** лежит рядом с changelog. Состав: пути модели и changelog, адрес БД,
  вердикт и перечень расхождений.
- **Ответ команды** — тот же документ.

### Документация

- **`docs/reconciliation.md`** (новый): что сравнивается и что нет, обратное отображение
  типов, виды расхождений с примером, порядок, `reconcile.json`, коды.
- **`docs/architecture.md`:** строка `forge reconcile` и ссылка на `reconciliation.md`.
  Версия 1.0.3.
- **`docs/migration.md`** не меняется: наблюдаемое поведение команд Миграции прежнее.

## Risks / Trade-offs

- [Перенос в общее ядро задевает код change 2] → перенос механический, поведение закреплено
  тестами change 2. Они переезжают вместе с кодом и обязаны пройти без правки утверждений.
- [Лишние индексы, внешние ключи и представления не видны сверке] → ограничение записано
  в `reconciliation.md`; БД управляется только Liquibase Forge, а первый срез такие объекты
  не создаёт.
- [Расхождение прямого и обратного отображения типов] → интеграционный тест «накат всех десяти
  типов — сверка без расхождений».
- [`format_type` меняет написание в новой версии PostgreSQL] → тот же интеграционный тест падает
  при смене `LBFR_POSTGRES_IMAGE`.

## Migration Plan

Миграции данных нет. Перенос в `forge.shared` выполняется одним шагом в начале change. Откат
change — возврат модулей в `migration` и удаление `reconciliation`; внешних потребителей
у перенесённых модулей нет.
