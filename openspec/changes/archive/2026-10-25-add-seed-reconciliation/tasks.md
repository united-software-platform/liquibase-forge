# Tasks

Задача: LBFR-028, тикет #20, часть 3 из 4. Опирается на `add-seed-format` (формат, `SeedValue`)
и `add-seed-migration` (changelog данных). Ветка выпуска — `release/0.4.0`, milestone `v0.4.0`.

## 1. Домен сверки строк

- [x] 1.1 Добавить в `Discrepancy` необязательное поле `key` и не выводить его в ответе `forge reconcile`; проверка: `uv run pytest tests/reconciliation tests/cli/test_reconcile.py` зелёные без правок тестов
- [x] 1.2 Реализовать в `src/forge/seeding/domain/` сравнение фактических строк с seed попытки по PK: `row_missing`, `row_unexpected`, `value_mismatch` по колонкам модели с NULL для пропущенных ключей, пустое ожидаемое для таблиц, убранных из seed, порядок по требованию «Расхождения seed идут в устойчивом порядке»; проверка: тесты `tests/seeding/domain/` по сценариям требований о строках, значениях, убранных таблицах и порядке

## 2. Чтение строк из PostgreSQL

- [x] 2.1 Реализовать в `src/forge/seeding/infrastructure/` чтение строк таблиц через `psycopg` с упорядочиванием по PK и переводом значений в нормализованную форму фабрикой `SeedValue` по таблице `design.md`; таблицы вне seed не читаются; проверка: модульные тесты перевода значений всех десяти типов, включая `Decimal('1.50')` и `datetime` со смещением

## 3. Сценарий и команда

- [x] 3.1 Реализовать `ReconcileSeedUseCase`: перечень тестовых до подключения, модель и принятый seed по умолчанию из корня принятого состояния, проверка seed попытки, строки, журнал через контракты и `JournalCheck` «Сверки», вердикт, `reconcile.json` рядом с changelog; ошибки входа и окружения — без `reconcile.json`; проверка: тесты `tests/seeding/application/` на фейках по требованиям о вердикте, результате и ошибках
- [x] 3.2 Добавить подкоманду `src/forge/cli/commands/reconcile_seed.py` и зарегистрировать её в `main.py`: ключи `--seed`, `--changelog`, `--accepted-seed`, `--model`, ответ `seed`/`changelog`/`database`/`verdict`/`discrepancies` с `key`, коды `0`/`1`/`2`, виды ошибок `settings_unavailable`, `database_not_allowed`, `database_unavailable`, `seed_unreadable`, `seed_invalid`, `accepted_seed_invalid`, `model_unreadable`, `model_invalid`, `changelog_unreadable`, `accepted_root_invalid`; проверка: `tests/cli/test_reconcile_seed.py`

## 4. Интеграция с PostgreSQL

- [x] 4.1 Интеграционный цикл на `lbfr-db-test`: накат модели и changelog данных со строкой всех десяти типов, `forge reconcile-seed` даёт `success`; затем ручная порча строки, лишняя строка и удалённая строка дают `value_mismatch`, `row_unexpected` и `row_missing`; убранная из seed таблица с оставшейся строкой даёт `row_unexpected`; проверка: тесты зелёные

## 5. Документация

- [x] 5.1 Написать `docs/seed-reconciliation.md` по DOC-014 и DOC-022: команда с таблицей кодов, что сравнивается, нормализация из БД, виды расхождений, порядок, пример `reconcile.json` с `key`, ограничения и допущения; проверка: тест документа сверяет пример `reconcile.json` с ответом команды на фикстуре
- [x] 5.2 Добавить `forge reconcile-seed` в таблицу команд `docs/architecture.md`; в `docs/reconciliation.md` добавить ссылку на сверку seed и оговорку, что `key` в ответе `forge reconcile` не выводится; дописать строки `LBFR-028, OpenSpec change add-seed-reconciliation` в конец таблиц версий (DOC-024); проверка: ссылки ведут на существующие разделы, новые строки последние

## 6. Проверка целиком

- [x] 6.1 Прогнать проверки из раздела «Проверки» `CONTRIBUTING.md`, включая интеграционные; проверка: все команды завершаются кодом `0`
- [x] 6.2 Подготовить коммит `LBFR-028: …` по GIT-009 без служебных подписей (GIT-012), показать состав и сообщение владельцу и коммитить только после его подтверждения (GIT-015, GIT-016); проверка: коммит в ветке `release/0.4.0`

## Workflow follow-up

- Архивировать изменение `add-seed-reconciliation` после слияния, затем начать `add-seed-operation`.
