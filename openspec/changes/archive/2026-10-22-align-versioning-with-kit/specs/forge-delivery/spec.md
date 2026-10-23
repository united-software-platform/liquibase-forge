# Spec Delta

## MODIFIED Requirements

### Requirement: Состав поставки задаёт перечень
Установщик MUST копировать в проект ровно пути, перечисленные в `delivery.txt` источника, и
никакие другие. Строка `источник → цель` SHALL класть источник по пути цели, строка без стрелки —
по тому же пути. Код CLI MUST попадать в `tools/forge/` целевого проекта: `src/forge`,
`pyproject.toml`, `uv.lock` и `VERSION` источника — в `tools/forge/src/forge`,
`tools/forge/pyproject.toml`, `tools/forge/uv.lock` и `tools/forge/VERSION`. Каждый источник
перечня MUST существовать в репозитории forge.

#### Scenario: Код CLI не трогает проект
- **WHEN** в целевом проекте есть собственные `pyproject.toml` и `src/`
- **THEN** после установки они не изменились, а CLI лежит в `tools/forge/`

#### Scenario: Тесты и документы не поставляются
- **WHEN** установка завершена
- **THEN** в проекте нет `tests/`, `openspec/` и `docs/` репозитория forge, и `README.md` проекта не изменён

#### Scenario: CLI собирается в установленном проекте
- **WHEN** установка завершена, и в проекте выполнено `sh tools/forge-env/forge.sh validate --model <модель>`
- **THEN** CLI собирается из `tools/forge/` с версией из `tools/forge/VERSION`, и код возврата совпадает с кодом `forge validate`

### Requirement: Манифест установки фиксирует поставленное
После установки MUST существовать `.forge-manifest.json` с версией forge, ref или пометкой
локального источника, временем установки и SHA-256 каждого файла поставки и каждого
маркированного блока в том виде, в каком их записал установщик. Версия forge SHALL браться
из файла `VERSION` источника.

#### Scenario: Состав манифеста
- **WHEN** установка `v0.2.0` завершена
- **THEN** `.forge-manifest.json` содержит ref `v0.2.0` и суммы всех файлов поставки и пяти блоков

#### Scenario: Версия в манифесте из VERSION
- **WHEN** в `VERSION` источника записано `0.2.0`
- **THEN** поле `forge_version` манифеста равно `0.2.0`
