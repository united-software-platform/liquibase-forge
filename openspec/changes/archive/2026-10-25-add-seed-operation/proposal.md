# Proposal

## Why

После трёх первых изменений у seed есть формат, changelog данных, откат и сверка, но нет
операции. Без неё LLM не может заполнить справочник по намерению, а владелец не получает
принятого `seed.yaml` и changelog данных для коммита. Кроме того, операция модели пока может
сломать принятый seed. Это четвёртая, завершающая часть операции seed (LBFR-028, #20).

## What Changes

- **Шаблоны беклогов.** Новые `forge-seed` (беклог операции) и `forge-seed-apply` (беклог
  попытки). Цикл тот же, что у модели: до трёх попыток «seed → `forge validate-seed` →
  `forge generate-seed` → `forge apply` → `forge reconcile-seed` → откат при `failure`»,
  режимы `interactive` и `auto`, стоп-знаки и гейты.
- **Навык `forge`.** Новые ключи `--seed <намерение>` и `--from <путь>`, ключ можно повторять.
  Ключ `--from` принимается только с `--seed`, путь — относительный внутри корня проекта.
  Правило «одна открытая операция» общее для операций модели и seed. `--abandon`, `--mode`
  и `--allow-drop` работают и для seed.
- **Вид операции.** Беклог операции seed лежит в `backlog/forge-seed/<штамп>/` с `kind: seed`
  во фронтматтере. Отсутствующее поле читается как `kind: model`. `forge status`, `forge report`,
  `forge stop`, `forge resume`, `forge close` и `forge abandon` понимают оба вида,
  а `forge status --latest` ищет открытую операцию в следах обоих видов.
- **Закрытие операции seed с `success`.** Принимает `seed.yaml` в `<корень>/seed.yaml`
  и changelog данных в `<корень>/changelog/<штамп>.yaml` с `include` в общий `master.yaml`.
- **Отчёт операции seed.** Для каждой таблицы показывает число вставленных, изменённых
  и удалённых строк. В перечне `destructive` — удалённые строки. В `commit.files` при `success`
  входит `<корень>/seed.yaml`.
- **Согласование с операцией модели** (`seed_conflict`). `forge generate` операции модели
  отклоняет кодом `1` с перечнем `seed_conflict`:
  - удаление таблицы из принятого seed;
  - новую колонку NOT NULL в таблице с seed-строками;
  - новые FK или набор `unique`, которым принятый seed не отвечает.

  Удаление колонки таблицы seed допускается. `forge close` операции модели убирает эту колонку
  из принятого `seed.yaml`.
- **Документация.** Кейс наполнения справочника в `docs/use-cases.md`, `docs/operation.md`,
  навык и ограничения `README.md`.

## Capabilities

### New Capabilities

- `forge-seed-operation`: операция seed — шаблоны беклогов, ключи навыка, цикл попыток,
  принятие `seed.yaml` и changelog данных, отчёт операции seed.

### Modified Capabilities

- `forge-operation-commands`:
  - `forge status --latest` ищет открытую операцию в следах `forge-model` и `forge-seed`;
  - статус и отчёт называют вид операции;
  - закрытие операции модели убирает удалённые колонки из принятого seed.
- `forge-migration`: `forge generate` отклоняет изменения модели, которые ломают принятый seed
  (`seed_conflict`).

## Impact

- Код:
  - `src/forge/operation/` — вид операции, поиск по двум следам, принятие seed, отчёт;
  - `src/forge/migration/` — проверка `seed_conflict` и правка принятого seed при закрытии
    операции модели;
  - подкоманды `status`, `report`, `close`, `abandon`, `stop`, `resume`.
- Шаблоны: `templates/forge-seed.md`, `templates/forge-seed-apply.md`. `forge-model.md`
  и `forge-apply.md` не меняются.
- Навык: `.claude/skills/forge/SKILL.md`.
- Поставка: `delivery.txt` и установщик получают новые шаблоны.
- Тесты:
  - модульные `tests/operation/`, `tests/migration/`, `tests/cli/`;
  - структурная проверка шаблонов (`backlog check-template`);
  - интеграционный цикл операции seed с отказом, откатом и принятием;
  - интеграционный накат `master.yaml` с changelog модели и данных на пустую БД.
- Документация: `docs/operation.md`, `docs/architecture.md`, `docs/domain.md`,
  `docs/use-cases.md`, `README.md`, `CONTRIBUTING.md`.
