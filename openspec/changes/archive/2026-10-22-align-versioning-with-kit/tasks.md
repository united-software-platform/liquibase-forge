# Tasks

## 1. Носитель номера

- [x] 1.1 Завести `VERSION` со значением `0.1.0`, перевести `pyproject.toml` на `dynamic = ["version"]` с `[tool.hatch.version]` по design.md и выполнить `uv lock`; проверка — тест в `tests/release/` подтверждает формат `VERSION`, отсутствие `version` в `[project]` и отсутствие номера у пакета `liquibase-forge` в `uv.lock`; `uv lock --check` проходит, `uv run python -c "import importlib.metadata as m; print(m.version('liquibase-forge'))"` печатает номер из `VERSION`
- [x] 1.2 Добавить в `delivery.txt` строку `VERSION -> tools/forge/VERSION` и перевести `install.sh` на чтение `forge_version` из `VERSION` с кодом `1` при отсутствующем или неразборчивом номере; проверка — тесты `tests/delivery/`: перечень содержит `VERSION`, `forge_version` манифеста равен содержимому `VERSION`, источник с неразборчивым `VERSION` даёт код `1` без записи

## 2. Релизный сценарий

- [x] 2.1 Добавить `.github/workflows/release.yml` по design.md: ручной запуск с вводом `bump`, гейт ветки `main`, разбор `VERSION`, гейт GIT-020, коммит `Релиз vX.Y.Z`, аннотированный тег, push, `gh release create --verify-tag`; права — только `contents: write`; проверка — тест в `tests/release/` разбирает YAML: единственный триггер `workflow_dispatch`, варианты `patch`/`minor`/`major`, права, порядок шагов «push тега → создание релиза»
- [x] 2.2 Проверить логику повышения номера на тексте сценария; проверка — тест исполняет скрипт шага разбора с временными `VERSION` и `GITHUB_OUTPUT`: `0.1.0` + `minor` → `0.2.0`, `1.4.3` + `major` → `2.0.0`, `1.4.3` + `patch` → `1.4.4`, `0.2` → ошибка с прочитанным значением

## 3. Документы

- [x] 3.1 Перевести бейдж версии `README.md` на `dynamic/regex` по `VERSION` ветки `main` с целью ссылки `./VERSION`; проверка — URL бейджа совпадает по форме с бейджем kit'а, номер в URL не записан (DGN-004)
- [x] 3.2 Дополнить `CONTRIBUTING.md`: раздел «Выпуск версии» (запуск сценария `release` из `main`, выбор разряда, право push бота в `main`, доведение Release вручную при сбое шага), строка карты бейджей, `VERSION` и `.github/workflows/` в «Устройство репозитория», команда тестов `tests/release` в «Проверки», строка в таблице версий по DOC-022; проверка — чтение по `rules/project-docs-rules.md`, каждая проверка названа одной командой (DGN-008), норма GIT-021 названа кодом (DGN-010)

## 4. Интеграционная проверка

- [x] 4.1 Сквозной прогон установщика: `sh install.sh --source .` во временном проекте с kit'ом, затем `sh tools/forge-env/forge.sh validate --model <пример модели>`; проверка — оба шага завершаются кодом `0`, `forge_version` манифеста равен `VERSION`, CLI собран из `tools/forge/` с версией из `tools/forge/VERSION`
- [x] 4.2 Прогнать проверки репозитория: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`, `sh tools/make-lint/check.sh`; проверка — все команды завершаются кодом `0`

## Workflow follow-up

- Реализовывать в ветке `release/v0.2.0`, коммиты — с кодом `LBFR-017` (задача GitHub #5).
- Закрыть задачу GitHub #5 по результату проверок 4.1 и 4.2.
- Синхронизировать дельты и архивировать изменение `/opsx:archive` после ревью.
- После слияния `release/v0.2.0` в `main` запустить сценарий `release` с разрядом `minor`, убедиться в коммите `Релиз v0.2.0`, теге и Release, затем проверить сетевую установку: `curl -fsSL …/install.sh | sh -s -- --ref v0.2.0` и запуск без `--ref`.
