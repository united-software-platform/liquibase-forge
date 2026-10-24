# Tasks

Задача: LBFR-028, тикет #20, часть 1 из 4 (`add-seed-format` → `add-seed-migration` →
`add-seed-reconciliation` → `add-seed-operation`). Ветка выпуска — `release/0.4.0`, milestone `v0.4.0`.

## 1. Общий обход узлов YAML

- [x] 1.1 Вынести из `src/forge/modeling/infrastructure/yaml_reader.py` в `src/forge/shared/infrastructure/yaml_nodes.py` помощники обхода по `design.md` («Общий обход узлов YAML выносится в `shared`»): теги и названия видов, получение единственного документа, сообщение синтаксической ошибки, проверку состава полей и повторных ключей; разборщик модели перевести на них без изменения поведения; проверка: `uv run pytest tests/modeling tests/cli/test_validate.py` зелёные без правок тестов

## 2. Домен seed

- [x] 2.1 Создать `src/forge/seeding/` со слоями `domain`, `application`, `infrastructure` и `tests/seeding/` с теми же подкаталогами; проверка: `uv run python -c "import forge.seeding"` проходит
- [x] 2.2 Реализовать объект-значение `SeedValue` и его фабрику по типу колонки модели с нормализованной формой из таблицы `design.md`: целые с диапазонами `integer`/`bigint`, `boolean`, `string` с `length`, `text`, `decimal` с `precision`/`scale` (строка или целое YAML), `date`, `timestamp`, `timestamp_tz` с обязательным смещением и приведением к UTC, `uuid` в нижнем регистре, `null`; коды `invalid_value` и `value_out_of_range`; проверка: тесты `tests/seeding/domain/` покрывают сценарии требований о значениях из `specs/forge-seed-data/spec.md`, в том числе равенство `"1.50"` и `"1.5"` и одного момента с разными смещениями
- [x] 2.3 Реализовать черновик seed и фабрику `Seed` над `DataModel`: таблица в модели (`unknown_table`), повтор таблицы (`duplicate_table`), колонки строки (`unknown_column`), NULL и пропуски NOT NULL и PK (`null_value`), повтор PK (`duplicate_primary_key`), повтор наборов `unique` без строк с NULL (`duplicate_unique`); строка с нарушенным значением в проверках ключей не участвует; проверка: тесты `tests/seeding/domain/` по сценариям требований о таблицах, строках, NOT NULL, PK и `unique`
- [x] 2.4 Реализовать проверку ссылок: цель FK вне seed (`unseeded_reference_table`, один раз на FK), неразрешённая ссылка без строк с NULL в колонках FK (`unresolved_reference`), циклы по сильно связным компонентам без петли «строка на себя» (`reference_cycle` на первой строке компоненты с перечнем строк цикла); проверка: тесты `tests/seeding/domain/` по сценариям требований о FK и циклах, включая самоссылку корневой строки

## 3. Чтение seed и сценарий проверки

- [x] 3.1 Реализовать разборщик `seed.yaml` в `src/forge/seeding/infrastructure/` на `yaml_nodes.py`: корень `version`/`tables`, поля `name`/`rows`, строки-отображения, сырые значения «тег + текст»; структурные коды `yaml_syntax`, `duplicate_key`, `missing_field`, `unknown_field`, `wrong_kind`, `unsupported_version`; нечитаемый файл — исключение контракта чтения; проверка: тесты `tests/seeding/infrastructure/` по сценариям требования «Seed описывается файлом YAML версии 1» и дата без кавычек читается как текст
- [x] 3.2 Реализовать `ValidateSeedUseCase` с входным и выходным контрактами: загрузка модели через `LoadModelUseCase`, разбор seed, нарушения трёх проходов в порядке `design.md` («Порядок проверки»); проверка: тесты `tests/seeding/application/` на фейках — порядок нарушений по сценарию «Несколько нарушений в разных таблицах» и побайтово равный повторный ответ

## 4. Команда CLI

- [x] 4.1 Добавить подкоманду `src/forge/cli/commands/validate_seed.py` и зарегистрировать её в `main.py`: `--seed`, необязательный `--model` с моделью по умолчанию из `settings.accepted_root()/model.yaml` и пустой моделью при отсутствии файла, ответ `seed`/`model`/`valid`/`violations`, коды `0`/`1`/`2`, виды ошибок `seed_unreadable`, `model_unreadable`, `model_invalid`, `accepted_root_invalid`; проверка: `tests/cli/test_validate_seed.py` по сценариям требований о команде и кодах возврата

## 5. Документация

- [x] 5.1 Написать `docs/seed-format.md` по DOC-014 и DOC-022: назначение и границы, пример, структура файла, значения по типам, NULL и ключи, ссылки и циклы, команда `forge validate-seed` с таблицей кодов возврата по образцу `docs/model-format.md`, коды нарушений, ограничения и допущения; положить пример в `tests/fixtures/seed/example.yaml` вместе с моделью-фикстурой; проверка: `tests/seeding/test_seed_format_doc.py` сверяет блок примера с фикстурой и проверяет, что пример корректен
- [x] 5.2 Ввести понятия «Seed», «Наполнение» и «Справочная таблица» в `docs/domain.md` (TERM-001, TERM-004) с контекстом «Наполнение» на карте контекстов; добавить строку `forge validate-seed` в таблицу команд `docs/architecture.md`; дописать в конец таблиц версий обоих документов строку с задачей `LBFR-028, OpenSpec change add-seed-format` (DOC-024); проверка: ссылки ведут на существующие разделы, новые строки последние

## 6. Проверка целиком

- [x] 6.1 Прогнать проверки из раздела «Проверки» `CONTRIBUTING.md`: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`; проверка: все команды завершаются кодом `0`
- [x] 6.2 Прогнать `sh tools/forge-env/forge.sh validate-seed --seed tests/fixtures/seed/example.yaml --model <модель-фикстура>`; проверка: код `0` и `valid: true`
- [x] 6.3 Подготовить коммит `LBFR-028: …` по GIT-009 без служебных подписей (GIT-012), показать состав и сообщение владельцу и коммитить только после его подтверждения (GIT-015, GIT-016); проверка: коммит в ветке `release/0.4.0`

## Workflow follow-up

- Архивировать изменение `add-seed-format` после слияния, затем начать `add-seed-migration`.
