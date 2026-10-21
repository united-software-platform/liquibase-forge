# Proposal

## Why

Проект установлен из SDD Developer Kit версии 1.4.3 (`.sdd-kit-manifest.json`, `kit_ref: main`),
а в репозитории kit'а выпущена версия 1.5.0 с новым правилом документов проекта и навыком
`project-docs`. Установщик kit'а не умеет сливать файлы: четыре файла поставки, в которые проект
внёс свои отличия под Liquibase Forge, он перезапишет целиком, и без отдельного разрешения
конфликтов обновление уничтожит окружение Forge.

## What Changes

- Обновление поставки kit'а в проекте с 1.4.3 до 1.5.0 штатным установщиком, закреплённым
  на теге `v1.5.0`, а не на подвижной ветке `main`.
- Новые файлы поставки: `rules/project-docs-rules.md` (правила `DGN-001`..`DGN-012`)
  и навык `.claude/skills/project-docs/` с тремя шаблонами.
- Обновление без конфликта: `CLAUDE.md` и `AGENTS.md` получают подключение
  `rules/project-docs-rules.md`; остальные файлы `rules/`, `tools/host-runner/` (кроме `runner.py`)
  и `tools/make-lint/` перезаписываются тем же содержимым.
- Пофайловое разрешение конфликтов слиянием для `.env.example`, `Makefile`, `docker-compose.yml`
  и `tools/host-runner/runner.py`: проектные отличия под Liquibase Forge сохраняются, изменения
  kit'а принимаются. На стороне kit'а эти файлы между 1.4.3 и 1.5.0 не менялись, поэтому
  результат слияния совпадает с текущей проектной версией.
- Манифест фиксирует версию 1.5.0, ссылку `v1.5.0` и контрольные суммы содержимого kit'а,
  чтобы следующее обновление снова распознало проектные отличия как конфликт.
- Повторное развёртывание инструментов SDD (`make init`), которое установщик называет
  следующим шагом после установки.

## Capabilities

### New Capabilities

- `sdd-kit-delivery`: состав и версия поставки SDD Developer Kit в проекте, сохранение
  проектных отличий в файлах поставки при обновлении kit'а и достоверность манифеста установки.

### Modified Capabilities

Нет. Требования `forge-environment` к `.env.example`, `docker-compose.yml` и целям `forge-env-*`
не меняются — обновление обязано их сохранить.

## Impact

- Файлы поставки в корне: `.sdd-kit-manifest.json`, `CLAUDE.md`, `AGENTS.md`, `rules/`,
  `tools/host-runner/`, `tools/make-lint/`, `.claude/skills/project-docs/`; конфликтные
  `.env.example`, `Makefile`, `docker-compose.yml`, `tools/host-runner/runner.py` по итогу
  содержат прежнюю проектную версию.
- Агент начинает применять правила `DGN-*` к `README.md`, `CONTRIBUTING.md` и документу кейсов
  проекта. Приведение документов проекта к этим правилам в изменение не входит.
- Код Liquibase Forge (`src/`, `tests/`, `tools/liquibase/`, `tools/forge-env/`, `docker/`)
  не затрагивается.
