# Spec Delta

## ADDED Requirements

### Requirement: Шаблон окружения содержит корень принятого состояния
`.env.example` MUST содержать `FORGE_ACCEPTED_DIR=db` с комментарием о назначении переменной.
Цель `make forge-env-sync` SHALL дописывать переменную в `.env`, где её нет, не меняя заданное
значение.

#### Scenario: Обновление существующей установки
- **WHEN** в `.env` нет `FORGE_ACCEPTED_DIR`, и пользователь запускает `make forge-env-sync`
- **THEN** в `.env` дописывается `FORGE_ACCEPTED_DIR=db`

#### Scenario: Значение уже задано
- **WHEN** в `.env` задано `FORGE_ACCEPTED_DIR=.forge/db`, и пользователь запускает `make forge-env-sync`
- **THEN** значение `.forge/db` остаётся без изменений

### Requirement: Репозиторий разработки не хранит принятое состояние
Репозиторий разработки Liquibase Forge MUST NOT содержать каталог `db/` ни в индексе git, ни
файлом-заглушкой. `.gitignore` репозитория SHALL исключать `/db/`, чтобы прогон при незаданной
`FORGE_ACCEPTED_DIR` не попал в коммит.

#### Scenario: Прогон без настройки
- **WHEN** в `.env` репозитория разработки нет `FORGE_ACCEPTED_DIR`, и `forge close` принимает модель в `db/`
- **THEN** `git status` не показывает файлов `db/`

#### Scenario: Чистый репозиторий
- **WHEN** выполняется `git ls-files db`
- **THEN** вывод пуст
