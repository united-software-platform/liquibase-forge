# Миграция seed: changelog данных, накат и откат

Как Liquibase Forge превращает seed в изменение строк тестовой БД: построение changelog данных
командой `forge generate-seed`, его накат `forge apply` и откат `forge rollback`. Формат seed
описан в [seed-format.md](./seed-format.md), накат и откат changelog — в [migration.md](./migration.md).

---

## Навигация

- [Разница seed](#разница-seed)
- [Порядок changeset](#порядок-changeset)
- [Группировка и идентичность](#группировка-и-идентичность)
- [Литералы значений](#литералы-значений)
- [Откат](#откат)
- [Неисполнимые изменения](#неисполнимые-изменения)
- [Удаления строк](#удаления-строк)
- [Пример](#пример)
- [Команда forge generate-seed](#команда-forge-generate-seed)
- [Ограничения и допущения](#ограничения-и-допущения)
- [Версионирование](#версионирование)

---

## Разница seed

Changelog данных — разница принятого seed и seed попытки. Строки сопоставляются по первичному
ключу (Primary Key, PK), значения сравниваются в нормализованной форме формата seed: `"1.50"`
и `"1.5"` колонки `decimal` — одно значение, и изменения строки нет.

| Строка | Изменение |
|--------|-----------|
| Только в seed попытки | Вставка всех колонок, пропущенные — явным `NULL` |
| В обоих seed с другими значениями | Изменение только отличающихся колонок по условию на PK |
| Только в принятом seed | Удаление по условию на PK |

Таблица, которая есть в принятом seed и отсутствует в seed попытки, теряет все свои строки
из принятого seed и перестаёт принадлежать seed. Смена PK строки — удаление старой строки
и вставка новой. Совпадающие seed дают пустой changelog `databaseChangeLog: []`.

Оба seed проверяются по одной модели, как у `forge validate-seed`: changelog строится только
из корректных seed.

---

## Порядок changeset

Changeset идут в порядке: вставки, затем изменения, затем удаления.

- **Вставки** идут от целевых строк внешнего ключа (Foreign Key, FK) к зависимым: родительская
  строка дерева вставляется раньше дочерней.
- **Изменения** идут в порядке таблиц и строк seed попытки.
- **Удаления** идут от зависимых строк к целевым, обратно вставкам.

При таком порядке каждая ссылка в промежуточном состоянии указывает на существующую строку:

- вставка ссылается только на строки итогового seed, а они уже есть или вставлены раньше;
- изменение ссылается на строки итогового seed, все они существуют после вставок;
- на удаляемые строки итоговый seed не ссылается, а прежние ссылки к моменту удаления сняты
  изменениями.

Так выполняется типовой сценарий «вывести строку справочника и перевести ссылки на новую»:
changelog вставляет новую строку, затем меняет ссылки, затем удаляет старую. Обратный порядок
«удаления → изменения → вставки» удалил бы строку раньше, чем с неё сняты ссылки, и нарушил бы FK.

Цена порядка — конфликты наборов `unique`, см. [Неисполнимые изменения](#неисполнимые-изменения).

---

## Группировка и идентичность

Строки упорядочиваются по графу ссылок FK: отдельно вставки и отдельно удаления. При равенстве
решает порядок таблиц и строк в seed: для удалений — в принятом seed, для вставок и изменений —
в seed попытки. Соседние в этом порядке строки одной таблицы и одного вида собираются в один
changeset.

Группировка идёт по строкам, а не по таблицам целиком. Поэтому changelog выполним и при цикле
на уровне таблиц без цикла строк: таблица `A` ссылается на `B`, а `B` — на `A`. Такая таблица
даёт несколько changeset. Цикл самих строк отклоняет проверка seed.

Идентичность changeset — как у changelog модели, см.
[migration.md](./migration.md#идентичность-changeset): `id` вида `<штамп>-<NN>` подряд с `01`,
`author: forge`, `logicalFilePath: db/changelog/<штамп>.yaml`, где штамп — `subject` беклога
операции seed. Повторная генерация с теми же аргументами даёт побайтово тот же файл.

---

## Литералы значений

Каждое значение пишется действием Liquibase по строке через `valueComputed` —
типизированным литералом:

| Значение | Запись |
|----------|--------|
| Не NULL | `'<нормализованная форма>'::<тип PostgreSQL>`, кавычки внутри удваиваются |
| NULL | `NULL` |

Тип PostgreSQL берётся из той же таблицы отображения, что в changelog модели: `VARCHAR(32)`,
`NUMERIC(12, 2)`, `TIMESTAMP WITH TIME ZONE`. Условие `where` действий `update` и `delete`
собирается из тех же литералов по всем колонкам PK: `code = 'draft'::VARCHAR(32)`.

Явный литерал с приведением однозначен. Атрибуты `value`, `valueNumeric` и `valueDate` не
используются: литерал из них строит сам Liquibase, и для `timestamp_tz` со смещением, `numeric`
с точностью и `uuid` результат зависит от его версии.

В YAML литерал записывается строкой в двойных кавычках: так `NULL` не читается как пустое
значение YAML. Значение `O'Reilly` становится литералом `'O''Reilly'::TEXT` и вставляется ровно
строкой `O'Reilly`, а не выполняется как SQL.

---

## Откат

Каждый changeset данных несёт явный блок `rollback`, построенный из принятого seed. Действия
отката идут в обратном порядке:

| Changeset | Откат строки |
|-----------|--------------|
| Вставка | Удаление по условию на PK |
| Изменение | Изменение тех же колонок к значениям принятого seed |
| Удаление | Вставка строки со всеми значениями принятого seed |

`forge rollback` снимает changeset данных тем же `rollback-count`, что и changeset модели, и затем
проверяет возврат строк проверками `row_absent`, `row_present` и `row_restored`, см.
[migration.md](./migration.md#проверка-возврата).

---

## Неисполнимые изменения

Новое значение набора `unique` у вставленной или изменённой строки может совпасть с принятым
значением другой строки, которая изменяется или удаляется. Такое изменение не выполнить без
временного нарушения набора, и ни один линейный порядок не решает все такие случаи.

| Случай | Пример |
|--------|--------|
| Обмен значениями | `draft` меняет `title` на `Новый`, а `new` — с `Новый` на `Черновик` |
| Повторное использование | Строка `archived` с `title: Архив` удаляется, новая `closed` получает `title: Архив` |

`forge generate-seed` отклоняет такие изменения кодом `1` с перечнем `unsupported`: код
`unique_conflict`, таблица, колонки набора и обе строки. Изменение разносится по двум операциям:
первая освобождает значение, вторая занимает его.

Временные значения и отложенные ограничения не используются: формат модели не описывает
`DEFERRABLE`, а временные значения видны в журнале и усложняют откат.

---

## Удаления строк

Ответ команды перечисляет удаляемые строки в `deleted_rows`: таблица и значения PK. Если беклог
операции в режиме `auto` имеет `allow_drop: false`, а changelog удаляет строки, команда
возвращает код `2` с видом `drop_not_allowed` и перечнем `objects` вида
`order_status[code=archived]` и не записывает changelog — как при удалении таблиц и колонок,
см. [migration.md](./migration.md#удаления). В режиме `interactive` удаление не требует согласия.

---

## Пример

Модель примера — справочник групп статусов и статусы заказа со ссылкой на группу и набором
`unique` по `title`:

```yaml
version: 1
tables:
  - name: status_group
    columns:
      - {name: code, type: string, length: 16}
      - {name: title, type: text, nullable: false}
    primary_key: [code]
  - name: order_status
    columns:
      - {name: code, type: string, length: 32}
      - {name: group_code, type: string, length: 16, nullable: false}
      - {name: title, type: text, nullable: false}
      - {name: fee, type: decimal, precision: 12, scale: 2}
    primary_key: [code]
    unique:
      - [title]
    foreign_keys:
      - columns: [group_code]
        references: {table: status_group, columns: [code]}
```

Принятый seed:

```yaml
version: 1
tables:
  - name: status_group
    rows:
      - {code: active, title: Активные}
  - name: order_status
    rows:
      - {code: draft, group_code: active, title: Черновик}
      - {code: archived, group_code: active, title: Архив, fee: "0.00"}
```

Seed попытки добавляет группу `closed` и статусы `paid` и `new`, меняет `title` статуса `draft`
и убирает статус `archived`:

```yaml
version: 1
tables:
  - name: status_group
    rows:
      - {code: active, title: Активные}
      - {code: closed, title: Закрытые}
  - name: order_status
    rows:
      - {code: draft, group_code: active, title: Набросок}
      - {code: paid, group_code: closed, title: Оплачен, fee: "12.50"}
      - {code: new, group_code: active, title: Новый}
```

Changelog данных операции со штампом `20261025-101500`. Группа `closed` вставляется раньше
статуса `paid`, который на неё ссылается; две вставки статусов собраны в один changeset,
и их откат идёт в обратном порядке:

```yaml
# Changelog данных операции 20261025-101500: построен forge generate-seed, вручную не правится
databaseChangeLog:
- changeSet:
    id: 20261025-101500-01
    author: forge
    logicalFilePath: db/changelog/20261025-101500.yaml
    changes:
    - insert:
        tableName: status_group
        columns:
        - column:
            name: code
            valueComputed: "'closed'::VARCHAR(16)"
        - column:
            name: title
            valueComputed: "'Закрытые'::TEXT"
    rollback:
    - delete:
        tableName: status_group
        where: "code = 'closed'::VARCHAR(16)"
- changeSet:
    id: 20261025-101500-02
    author: forge
    logicalFilePath: db/changelog/20261025-101500.yaml
    changes:
    - insert:
        tableName: order_status
        columns:
        - column:
            name: code
            valueComputed: "'paid'::VARCHAR(32)"
        - column:
            name: group_code
            valueComputed: "'closed'::VARCHAR(16)"
        - column:
            name: title
            valueComputed: "'Оплачен'::TEXT"
        - column:
            name: fee
            valueComputed: "'12.5'::NUMERIC(12, 2)"
    - insert:
        tableName: order_status
        columns:
        - column:
            name: code
            valueComputed: "'new'::VARCHAR(32)"
        - column:
            name: group_code
            valueComputed: "'active'::VARCHAR(16)"
        - column:
            name: title
            valueComputed: "'Новый'::TEXT"
        - column:
            name: fee
            valueComputed: "NULL"
    rollback:
    - delete:
        tableName: order_status
        where: "code = 'new'::VARCHAR(32)"
    - delete:
        tableName: order_status
        where: "code = 'paid'::VARCHAR(32)"
- changeSet:
    id: 20261025-101500-03
    author: forge
    logicalFilePath: db/changelog/20261025-101500.yaml
    changes:
    - update:
        tableName: order_status
        columns:
        - column:
            name: title
            valueComputed: "'Набросок'::TEXT"
        where: "code = 'draft'::VARCHAR(32)"
    rollback:
    - update:
        tableName: order_status
        columns:
        - column:
            name: title
            valueComputed: "'Черновик'::TEXT"
        where: "code = 'draft'::VARCHAR(32)"
- changeSet:
    id: 20261025-101500-04
    author: forge
    logicalFilePath: db/changelog/20261025-101500.yaml
    changes:
    - delete:
        tableName: order_status
        where: "code = 'archived'::VARCHAR(32)"
    rollback:
    - insert:
        tableName: order_status
        columns:
        - column:
            name: code
            valueComputed: "'archived'::VARCHAR(32)"
        - column:
            name: group_code
            valueComputed: "'active'::VARCHAR(16)"
        - column:
            name: title
            valueComputed: "'Архив'::TEXT"
        - column:
            name: fee
            valueComputed: "'0'::NUMERIC(12, 2)"
```

---

## Команда forge generate-seed

```bash
forge generate-seed --seed <seed попытки> [--accepted-seed <принятый seed>] [--model <модель>] \
  --operation <беклог операции> --out <каталог попытки>/changelog.yaml
```

Без `--accepted-seed` принятым seed служит `seed.yaml` корня принятого состояния
`FORGE_ACCEPTED_DIR` (по умолчанию `db/seed.yaml`), без `--model` — `model.yaml` того же корня,
см. [operation.md](./operation.md#принятое-состояние). Нет файла принятого seed — принятый seed
пуст, и changelog вставляет все строки seed попытки. Нет файла модели по умолчанию — модель пуста.

| Код | Когда | Ответ |
|-----|-------|-------|
| `0` | Changelog данных записан | `changelog`, `logical_file_path`, перечень `changesets` с `id`, видом (`insert_rows`, `update_rows`, `delete_rows`), таблицей и числом строк `rows`, перечень `deleted_rows` с таблицей и PK `key` |
| `1` | Seed попытки нарушает формат или изменения неисполнимы | `changelog: null`, `violations` как у `forge validate-seed` либо `unsupported`; прежний файл `--out` удалён |
| `2` | Нет беклога операции или `subject` не штамп; seed попытки или модель не прочитать; модель некорректна; принятый seed есть, но не читается или некорректен; без `--accepted-seed` или `--model` некорректен `FORGE_ACCEPTED_DIR`; удаления строк в режиме `auto` без согласия операции | Объект `error` с видом `operation_unavailable`, `seed_unreadable`, `model_unreadable`, `accepted_model_invalid`, `accepted_seed_invalid`, `accepted_root_invalid` или `drop_not_allowed` с перечнем `objects`; при `drop_not_allowed` прежний файл `--out` удалён |

Накат changelog данных — та же команда `forge apply`, что для changelog модели: шлюз Liquibase
от содержимого changelog не зависит. Принятые changelog данных накатываются запасным путём
отката в составе `master.yaml` наравне с changelog модели.

---

## Ограничения и допущения

- **Допущение:** таблица, впервые попадающая в seed, в рабочей БД пуста. Строки рабочей БД,
  не принадлежащие seed, ломают вставку по PK → накат завершается ошибкой Liquibase.
- **Риск:** строка с символом NUL проходит формат seed, но PostgreSQL её отвергает → накат
  завершается ошибкой Liquibase, попытка неуспешна с диагностикой. Запрет NUL в формате —
  кандидат в правку формата.
- **Ограничение:** размер changelog не ограничен: одна строка — одно действие Liquibase, и большой
  справочник даёт длинный changelog. Справочные данные малы по природе.
- **Ограничение:** значения набора `unique`, освобождаемые и занимаемые в одной операции,
  отклоняются, см. [Неисполнимые изменения](#неисполнимые-изменения).
- **Риск:** изменение значения набора `unique`, на который ведёт FK других строк, отказом
  `unsupported` не ловится → накат или удаление нарушают FK, накат завершается ошибкой Liquibase.
  Ссылки по PK этому не подвержены: смена PK — удаление и вставка.
- **Ограничение:** проверка возврата смотрит только строки, которые затрагивает changelog
  попытки, а не все строки таблиц seed.

---

## Версионирование

| Версия | Дата | Задача | Агент | Модель | Описание изменений |
|--------|------|--------|-------|--------|--------------------|
| 1.0.0 | 2026-10-24 | LBFR-028, OpenSpec change `add-seed-migration` | Claude Code | Claude Opus 5.5 | Начальное создание: разница seed по PK в нормализованной форме, порядок «вставки → изменения → удаления» и его обоснование, группировка строк и идентичность changeset, типизированные литералы `valueComputed`, явный откат, отказ `unsupported` при конфликтах `unique`, удаления строк и согласие операции, пример с эталонным changelog, команда `forge generate-seed` с кодами, ограничения и допущения |
