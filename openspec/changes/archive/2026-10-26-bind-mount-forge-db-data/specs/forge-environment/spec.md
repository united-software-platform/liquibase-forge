# Spec Delta

## ADDED Requirements

### Requirement: Данные целевой БД хранятся в каталоге проекта
Сервис `lbfr-db` MUST хранить каталог данных PostgreSQL в каталоге проекта `data/lbfr-db`,
смонтированном в контейнер. Именованный том Docker для данных `lbfr-db` SHALL NOT объявляться.
Сервер тестов `lbfr-db-test` MUST по-прежнему хранить данные в `tmpfs`.

#### Scenario: Монтирование в итоговой конфигурации
- **WHEN** проверяется итоговая конфигурация Compose
- **THEN** у `lbfr-db` каталог `/var/lib/postgresql/data` смонтирован из `<корень проекта>/data/lbfr-db`, а секции `volumes` верхнего уровня с томом `lbfr-db-data` нет

#### Scenario: Данные переживают пересоздание контейнера
- **WHEN** в целевой БД создана таблица, а контейнер `lbfr-db` удалён и поднят заново `make forge-env-up`
- **THEN** таблица на месте, а её файлы лежат в `data/lbfr-db` проекта

#### Scenario: Данные не зависят от имени Compose-проекта
- **WHEN** пользователь меняет `COMPOSE_PROJECT_NAME` в `.env` и снова запускает `make forge-env-up`
- **THEN** `lbfr-db` поднимается на прежних данных из `data/lbfr-db`

#### Scenario: Сервер тестов не пишет в каталог проекта
- **WHEN** проверяется итоговая конфигурация Compose
- **THEN** у `lbfr-db-test` каталог данных смонтирован как `tmpfs`, а не из каталога проекта

### Requirement: Подъём окружения создаёт каталог данных целевой БД
Цель `make forge-env-up` MUST создавать каталог `data/lbfr-db` проекта, если его нет, до запуска
контейнеров. Существующий каталог и его содержимое SHALL NOT меняться.

#### Scenario: Первый подъём
- **WHEN** в проекте нет каталога `data/`, и пользователь запускает `make forge-env-up`
- **THEN** появляется `data/lbfr-db`, а `lbfr-db` поднимается до `healthy` с пустой БД `FORGE_DB_NAME`

#### Scenario: Повторный подъём
- **WHEN** `data/lbfr-db` уже содержит данные БД, и пользователь снова запускает `make forge-env-up`
- **THEN** `lbfr-db` поднимается на существующих данных

#### Scenario: Свои файлы проекта в data
- **WHEN** в каталоге `data/` проекта лежат файлы самого проекта, и пользователь запускает `make forge-env-up`
- **THEN** эти файлы остаются без изменений

### Requirement: Каталог данных целевой БД не попадает в git
`.gitignore` репозитория разработки и блок forge в `.gitignore` целевого проекта MUST исключать
`/data/lbfr-db/`. Остальное содержимое каталога `data/` SHALL NOT исключаться поставкой forge.

#### Scenario: Подъём окружения в целевом проекте
- **WHEN** forge установлен в проект, и `make forge-env-up` наполнил `data/lbfr-db`
- **THEN** `git status` не показывает файлов `data/lbfr-db`

#### Scenario: Файлы проекта в data остаются в git
- **WHEN** в целевом проекте есть `data/fixtures.csv`
- **THEN** `git status` показывает этот файл, а `git check-ignore data/fixtures.csv` ничего не выводит
