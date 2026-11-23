# Spec Delta

## MODIFIED Requirements

### Requirement: Накат выполняется через шлюз на БД из перечня тестовых

`forge apply --changelog <путь>` MUST накатывать changelog на БД из `FORGE_DB_*` только через
шлюз Liquibase. БД вне `FORGE_TEST_DB_ALLOWLIST` SHALL отклоняться кодом `2` до запуска
Liquibase.

#### Scenario: Успешный накат

- **WHEN** changelog корректен, БД входит в перечень тестовых, Liquibase с драйвером доступны
- **THEN** команда возвращает код `0`, а рядом с changelog записан `apply.json` с кодом исхода и выводом Liquibase

#### Scenario: БД вне перечня

- **WHEN** `FORGE_DB_*` указывает на БД, которой нет в `FORGE_TEST_DB_ALLOWLIST`
- **THEN** команда возвращает код `2`, Liquibase не запускается, `apply.json` не записан

## REMOVED Requirements

### Requirement: Исход наката различает ошибку Liquibase и ошибку окружения

**Reason**: Сценарий «Раннер недоступен» описывает среду, которой больше нет: раннер удалён,
а ошибкой окружения стал недоступный Liquibase.

**Migration**: Заменена требованием «Исход наката различает ошибку Liquibase и ошибку среды»
в этом же изменении.

## ADDED Requirements

### Requirement: Исход наката различает ошибку Liquibase и ошибку среды

Ошибка Liquibase MUST давать код `1` и записанный `apply.json`. Отсутствующий Liquibase или
драйвер, отказ шлюза и не заданные переменные окружения SHALL давать код `2` без `apply.json`.

#### Scenario: Ошибка Liquibase

- **WHEN** Liquibase завершает накат ошибкой
- **THEN** команда возвращает код `1`, `apply.json` содержит диагностику Liquibase

#### Scenario: Liquibase недоступен

- **WHEN** Liquibase не найден в `PATH` либо файл драйвера не загружен
- **THEN** команда возвращает код `2` с указанием на Liquibase, `apply.json` не записан
