# Миграция: changelog, накат и откат

Как Liquibase Forge превращает модель данных в изменение схемы тестовой БД: построение changelog
командой `forge generate`, накат `forge apply` и откат `forge rollback`. Формат модели описан
в [model-format.md](./model-format.md), устройство системы — в [architecture.md](./architecture.md).

---

## Навигация

- [Changelog](#changelog)
- [Удаления](#удаления)
- [Идентичность changeset](#идентичность-changeset)
- [Неподдерживаемые изменения](#неподдерживаемые-изменения)
- [Команда forge generate](#команда-forge-generate)
- [Накат](#накат)
- [Откат](#откат)
- [Проверка возврата](#проверка-возврата)
- [Запасной путь](#запасной-путь)
- [Ограничения и допущения](#ограничения-и-допущения)
- [Версионирование](#версионирование)

---

## Changelog

Changelog — разница между принятой моделью `db/model.yaml` и моделью попытки: новые и удалённые
таблицы и колонки. Если принятой модели нет, она считается пустой, и changelog создаёт все таблицы
модели. Удаления описаны в разделе [Удаления](#удаления).

Принятая модель:

```yaml
version: 1
tables:
  - name: customer
    columns:
      - {name: id, type: uuid}
    primary_key: [id]
```

Модель попытки:

```yaml
version: 1
tables:
  - name: customer
    columns:
      - {name: id, type: uuid}
      - {name: email, type: string, length: 255, nullable: false}
    primary_key: [id]
  - name: invoice_line
    columns:
      - {name: line_no, type: integer}
      - {name: invoice_id, type: bigint}
      - {name: amount, type: decimal, precision: 12, scale: 2}
    primary_key: [invoice_id, line_no]
```

Changelog операции со штампом `20261017-153000`:

```yaml
# Changelog операции 20261017-153000: построен forge generate, вручную не правится
databaseChangeLog:
- changeSet:
    id: 20261017-153000-01
    author: forge
    logicalFilePath: db/changelog/20261017-153000.yaml
    changes:
    - addColumn:
        tableName: customer
        columns:
        - column:
            name: email
            type: VARCHAR(255)
            constraints:
              nullable: false
- changeSet:
    id: 20261017-153000-02
    author: forge
    logicalFilePath: db/changelog/20261017-153000.yaml
    changes:
    - createTable:
        tableName: invoice_line
        columns:
        - column:
            name: line_no
            type: INTEGER
            constraints:
              nullable: false
        - column:
            name: invoice_id
            type: BIGINT
            constraints:
              nullable: false
        - column:
            name: amount
            type: NUMERIC(12, 2)
    - addPrimaryKey:
        tableName: invoice_line
        columnNames: invoice_id, line_no
        constraintName: pk_invoice_line
```

Тест проверяет, что `forge generate` строит из этих моделей ровно этот changelog.

Правила построения:

- **Порядок.** Сначала удаления: удалённые таблицы в порядке принятой модели, затем удалённые
  колонки по таблицам и колонкам принятой модели. Затем добавления в порядке таблиц модели попытки,
  внутри таблицы — в порядке колонок. Номера `id` идут подряд через весь changelog.
- **Таблица.** Новая таблица — один changeset из `createTable` и `addPrimaryKey`. Первичный ключ
  (Primary Key, PK) создаётся отдельно, чтобы сохранить порядок колонок `primary_key` модели;
  признак `primaryKey` в колонках построил бы ключ в порядке колонок таблицы.
- **Колонка.** Новая колонка существующей таблицы — один changeset `addColumn`.
- **NOT NULL.** `nullable: false` получают колонки PK и колонки с `nullable: false`.
- **Типы.** Отображение типов в PostgreSQL — по таблице [model-format.md](./model-format.md#типы-колонок).
  `timestamp` пишется как `TIMESTAMP WITHOUT TIME ZONE`, `timestamp_tz` — как
  `TIMESTAMP WITH TIME ZONE`.
- **Совпадающие модели.** Changelog без changeset: `databaseChangeLog: []`.
- **Повторяемость.** Повторная генерация с теми же аргументами даёт побайтово тот же файл.

Откат changeset создания таблицы и добавления колонки Liquibase выводит сам. Откат changeset
удаления задан явно — см. [Удаления](#удаления).

---

## Удаления

Удалённая таблица и удалённая колонка существующей таблицы дают отдельные changeset `dropTable`
и `dropColumn`. Ниже модель, из которой удалены таблица `invoice_line` и колонка `customer.email`,
а таблица `payment` добавлена.

Принятая модель:

```yaml
version: 1
tables:
  - name: customer
    columns:
      - {name: id, type: uuid}
      - {name: email, type: string, length: 255, nullable: false}
    primary_key: [id]
  - name: invoice_line
    columns:
      - {name: line_no, type: integer}
      - {name: invoice_id, type: bigint}
      - {name: amount, type: decimal, precision: 12, scale: 2}
    primary_key: [invoice_id, line_no]
```

Модель попытки:

```yaml
version: 1
tables:
  - name: customer
    columns:
      - {name: id, type: uuid}
    primary_key: [id]
  - name: payment
    columns:
      - {name: id, type: uuid}
      - {name: amount, type: decimal, precision: 12, scale: 2, nullable: false}
    primary_key: [id]
```

Changelog операции со штампом `20261017-153000`:

```yaml
# Changelog операции 20261017-153000: построен forge generate, вручную не правится
databaseChangeLog:
- changeSet:
    id: 20261017-153000-01
    author: forge
    logicalFilePath: db/changelog/20261017-153000.yaml
    changes:
    - dropTable:
        tableName: invoice_line
    rollback:
    - createTable:
        tableName: invoice_line
        columns:
        - column:
            name: line_no
            type: INTEGER
            constraints:
              nullable: false
        - column:
            name: invoice_id
            type: BIGINT
            constraints:
              nullable: false
        - column:
            name: amount
            type: NUMERIC(12, 2)
    - addPrimaryKey:
        tableName: invoice_line
        columnNames: invoice_id, line_no
        constraintName: pk_invoice_line
- changeSet:
    id: 20261017-153000-02
    author: forge
    logicalFilePath: db/changelog/20261017-153000.yaml
    changes:
    - dropColumn:
        tableName: customer
        columnName: email
    rollback:
    - addColumn:
        tableName: customer
        columns:
        - column:
            name: email
            type: VARCHAR(255)
            constraints:
              nullable: false
- changeSet:
    id: 20261017-153000-03
    author: forge
    logicalFilePath: db/changelog/20261017-153000.yaml
    changes:
    - createTable:
        tableName: payment
        columns:
        - column:
            name: id
            type: UUID
            constraints:
              nullable: false
        - column:
            name: amount
            type: NUMERIC(12, 2)
            constraints:
              nullable: false
    - addPrimaryKey:
        tableName: payment
        columnNames: id
        constraintName: pk_payment
```

Тест проверяет, что `forge generate` строит из этих моделей ровно этот changelog.

Правила удалений:

- **Откат.** Блок `rollback` changeset восстанавливает структуру объекта по принятой модели: таблицу
  с колонками, типами, NOT NULL и ключом `pk_<таблица>`, колонку — с типом и NOT NULL. Данные
  удалённого объекта откат не восстанавливает.
- **Колонка ключа.** Удаление колонки первичного ключа не даёт `dropColumn` и отклоняется как смена
  ключа — см. [Неподдерживаемые изменения](#неподдерживаемые-изменения).
- **Согласие в `auto`.** Changelog с удалениями строится в режиме `auto` только при `allow_drop: true`
  в беклоге операции, иначе `forge generate` отвечает кодом `2` с видом `drop_not_allowed` — см.
  [operation.md](./operation.md#согласие-на-удаления).

> **Внимание:** удаление стирает данные тестовой БД. Принятый changelog с удалением остаётся
> в `master.yaml` навсегда, и при переносе на рабочую БД он удалит данные. Ограничение «только
> тестовая БД» сохраняется.

---

## Идентичность changeset

| Атрибут | Значение | Зачем |
|---------|----------|-------|
| `id` | `<штамп>-<NN>`, номер от `01`, минимум две цифры | Однозначен в пределах операции |
| `author` | `forge` | Отличает changeset Liquibase Forge |
| `logicalFilePath` | `db/changelog/<штамп>.yaml` у каждого changeset | Запись `DATABASECHANGELOG` одинакова, накатан ли файл из следа попытки или из корня принятого состояния, и каков этот корень |

Штамп — `subject` беклога операции в виде `YYYYMMDD-HHMMSS`. Все попытки одной операции получают
одинаковые `id`. Конфликта в журнале нет: неуспешная попытка откатывается до начала следующей.

---

## Неподдерживаемые изменения

Changelog выражает новые и удалённые таблицы и колонки. Смена типа, итоговой допустимости NULL
и первичного ключа — неподдерживаемое изменение: `forge generate` отклоняет модель кодом `1`
и перечисляет все такие изменения сразу в поле ответа `non_additive`.

| Код | Когда |
|-----|-------|
| `column_type_changed` | У колонки другой тип или другие параметры типа |
| `column_nullable_changed` | У колонки другая итоговая допустимость NULL |
| `primary_key_changed` | У таблицы другой набор или порядок колонок PK, в том числе удалена колонка PK |

Уточнения:

- **Переименование** неотличимо от удаления с добавлением: changelog удаляет прежнюю колонку
  и добавляет новую.
- **Итоговая допустимость NULL** учитывает PK: явное `nullable: false` у колонки PK изменением
  не считается.
- **Порядок колонок таблицы** изменением не считается.
- **Новая колонка с `nullable: false`** в существующей таблице разрешена. На непустой таблице
  накат завершится ошибкой Liquibase, и попытка станет неуспешной с понятной диагностикой.

---

## Команда forge generate

```bash
forge generate --model <модель попытки> [--accepted <принятая модель>] \
  --operation <беклог операции> --out <каталог попытки>/changelog.yaml
```

Без `--accepted` принятой моделью служит `model.yaml` корня принятого состояния
`FORGE_ACCEPTED_DIR` (по умолчанию `db/model.yaml`), см.
[operation.md](./operation.md#принятое-состояние). Нет файла — принятая модель пуста.

| Код | Когда | Ответ |
|-----|-------|-------|
| `0` | Changelog записан | `changelog`, `logical_file_path`, перечень `changesets` с `id`, видом (`create_table`, `add_column`, `drop_table`, `drop_column`), таблицей и колонкой |
| `1` | Модель попытки нарушает формат или требует неподдерживаемых изменений | `changelog: null`, `violations` как у `forge validate` либо `non_additive`; прежний файл `--out` удалён |
| `2` | Нет беклога операции или `subject` не штамп; модель попытки не прочитать; принятая модель есть, но некорректна; без `--accepted` некорректен `FORGE_ACCEPTED_DIR`; удаления в режиме `auto` без согласия операции | Объект `error` с видом `operation_unavailable`, `model_unreadable`, `accepted_model_invalid`, `accepted_root_invalid` или `drop_not_allowed` с перечнем `objects`; при `drop_not_allowed` прежний файл `--out` удалён |

При отказе прежний changelog удаляется, чтобы устаревший файл нельзя было накатить.

---

## Накат

```bash
forge apply --changelog <каталог попытки>/changelog.yaml
```

Агент работает без Docker и Liquibase, поэтому накат идёт через шлюз на хосте:

1. Команда берёт адрес целевой БД из `FORGE_DB_HOST`, `FORGE_DB_PORT`, `FORGE_DB_NAME`
   и проверяет его по `FORGE_TEST_DB_ALLOWLIST`. БД вне перечня отклоняется до обращения
   к раннеру.
1. Команда пишет запрос `.forge/liquibase-request.json` и вызывает цель раннера
   `liquibase-update`. Шлюз повторно проверяет перечень и запускает Liquibase в контейнере
   `lbfr-liquibase`.
1. Команда читает `.forge/liquibase-result.json` и принимает его, только если идентификатор
   запроса совпадает.

| Код | Когда | `apply.json` |
|-----|-------|--------------|
| `0` | Liquibase выполнил накат | Записан |
| `1` | Liquibase завершился ошибкой; диагностика продублирована в stderr | Записан |
| `2` | Переменные окружения не заданы, БД вне перечня, раннер недоступен, шлюз отказал, результат не прочитан или относится к другому запросу | Не записан |

`apply.json` лежит рядом с changelog. В нём путь changelog, адрес БД, `request_id`, код исхода,
вывод и диагностика Liquibase. При коде `2` файла нет намеренно: беклог попытки по его наличию
считает накат выполненным.

Код `1` — штатный путь: за ним идёт сверка с вердиктом `failure` и откат. Из нескольких changeset
могли примениться не все; откат снимает ровно применённые.

Вид ошибки в ответе с кодом `2`: `settings_unavailable`, `database_not_allowed`,
`runner_unavailable`, `gateway_refused`, `gateway_result_invalid`.

---

## Откат

```bash
forge rollback --operation <беклог операции> --attempt <N>
```

Команда не оставляет в тестовой БД неподтверждённых изменений попытки `N`. Решение принимается
по вердикту попытки во фронтматтере беклога операции и по журналу `DATABASECHANGELOG`.

```mermaid
flowchart TD
    V{"verdict.attempt_N"} -->|success| N["код 0, ничего не меняется"]
    V -->|failure или null| J["записи журнала с FILENAME попытки"]
    J -->|нет записей| C["проверка возврата"]
    J -->|k записей| T{"хвост журнала и changelog есть"}
    T -->|да| L["шлюз: rollback-count k"]
    T -->|нет| R["пересоздание БД и накат master.yaml"]
    L -->|код 0| C
    L -->|код 1| R
    R --> C
    C --> W["rollback.json, код 0 или 1"]
```

- **Записи попытки.** Это строки журнала с `FILENAME` = `db/changelog/<штамп>.yaml`. Предыдущие
  попытки операции к этому моменту откатаны, у принятых changelog другие штампы.
- **Частичный накат.** Откатывается столько changeset, сколько их фактически записано в журнал,
  а не сколько их в changelog.
- **Хвост журнала.** Последние `k` записей по порядку исполнения — ровно записи попытки, и их `id`
  есть в changelog попытки. Иначе Liquibase rollback не вызывается.
- **Вердикт `success`.** Команда только печатает ответ с `action: none` и не пишет `rollback.json`.

| Код | Когда |
|-----|-------|
| `0` | Возврат подтверждён, откатывать было нечего, или вердикт `success` |
| `1` | Возврат не подтверждён: проверка или накат принятого состояния не прошли |
| `2` | Нет беклога операции, переменные окружения не заданы, БД вне перечня, БД или раннер недоступны, шлюз отказал |

`rollback.json` пишется в каталог попытки. В нём номер попытки и вердикт, действие (`none_applied`,
`liquibase_rollback` или `recreate_database`), число откатанных changeset, результат шлюза,
причина и итог запасного пути, перечень проверок и итог `verified`.

---

## Проверка возврата

После отката команда проверяет:

| Проверка | Что подтверждает |
|----------|------------------|
| `journal_clean` | В журнале нет записей changelog попытки |
| `table_absent` | Нет таблицы, которую создаёт changelog попытки |
| `column_absent` | Нет колонки, которую добавляет changelog попытки |
| `table_present` | Есть таблица, которую удаляет changelog попытки: откат вернул её |
| `column_present` | Есть колонка, которую удаляет changelog попытки: откат вернул её |
| `accepted_restored` | Только на запасном пути: принятый `master.yaml` накатан или его нет |
| `attempt_objects` | Только без changelog попытки: объекты попытки не проверить, проверен один журнал |

Проверка смотрит только объекты попытки, а не всю схему. Полное сравнение схемы с моделью —
сверка `forge reconcile`.

---

## Запасной путь

Запасной путь выбирается, если откат Liquibase завершился ошибкой, записи попытки не являются
хвостом журнала или changelog попытки отсутствует:

1. Перечень тестовых проверяется повторно, вплотную к удалению БД.
1. Под служебной БД `postgres` того же сервера выполняются `DROP DATABASE … WITH (FORCE)`
   и `CREATE DATABASE` с учётными данными `FORGE_DB_USER` и `FORGE_DB_PASSWORD`.
1. Если есть `master.yaml` корня принятого состояния (`<корень>/changelog/master.yaml`),
   он накатывается через шлюз. Если нет, принятого состояния нет, и БД остаётся пустой.

> **Внимание:** запасной путь удаляет целевую БД. Он выполняется только для БД из
> `FORGE_TEST_DB_ALLOWLIST`, а пользователю `FORGE_DB_USER` нужно право создавать БД.

---

## Ограничения и допущения

- **Ограничение:** только PostgreSQL. Changelog добавляет и удаляет таблицы и колонки; смена типа,
  NULL и первичного ключа не поддерживается.
- **Допущение:** схема целевой БД полностью управляется Liquibase, а принятая модель описывает её
  состояние.
- **Ограничение:** корень проекта — текущий каталог: команды вызываются из корня, иначе шлюз
  не найдёт changelog, а команда — файл результата.
- **Ограничение:** файлы `.forge/` общие, раннер однопоточный, поэтому команды `forge apply`
  и `forge rollback` не запускаются параллельно.
- **Риск:** Liquibase может перевести имя типа иначе, чем ожидается → интеграционный тест
  сравнивает фактические типы колонок с таблицей отображения.

---

## Версионирование

| Версия | Дата | Задача | Агент | Модель | Описание изменений |
|--------|------|--------|-------|--------|--------------------|
| 1.0.0 | 2026-10-18 | OpenSpec change `forge-migration` | Claude Code | Claude Opus 5.5 | Начальное создание: правила построения changelog с примером, идентичность changeset, состав добавляющих изменений и коды неаддитивных, команда `forge generate`, накат и `apply.json`, откат со схемой решений, проверка возврата, запасной путь с пересозданием БД |
| 1.0.1 | 2026-10-21 | OpenSpec change `configurable-accepted-root` | Claude Code | Claude Opus 5.5 | Команда `forge generate`: `--accepted` необязателен, умолчание — `model.yaml` корня принятого состояния `FORGE_ACCEPTED_DIR`, код `2` с видом `accepted_root_invalid` при некорректном корне; запасной путь накатывает `master.yaml` корня принятого состояния вместо `db/changelog/master.yaml`; уточнено, что `logicalFilePath` не зависит от корня |
| 1.0.2 | 2026-10-22 | OpenSpec change `add-drop-operations` | Claude Code | Claude Opus 5.5 | Удаление таблиц и колонок: раздел «Удаления» с примером и блоками `rollback`, порядок changeset, раздел «Неподдерживаемые изменения» без `table_removed`/`column_removed`, виды `drop_table`/`drop_column` и отказ `drop_not_allowed` в `forge generate`, проверки возврата `table_present`/`column_present`, ограничения |
