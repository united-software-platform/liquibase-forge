# Spec Delta

## REMOVED Requirements

### Requirement: Целевая БД публикуется на хост

**Reason**: Сервис `lbfr-db` и публикация его порта удаляются вместе с Docker Compose.
Целевая БД forge — база на общем экземпляре PostgreSQL workspace, который слушает
фиксированный localhost-порт.

**Migration**: Клиент с хоста подключается к `localhost:<PG_PORT>` с учётными данными
`FORGE_DB_USER` и `FORGE_DB_PASSWORD`; переменная `FORGE_DB_HOST_PORT` удаляется.

### Requirement: Шаблон окружения содержит хостовый порт целевой БД

**Reason**: Переменная `FORGE_DB_HOST_PORT` исчезает вместе с публикацией порта, а цели
`make forge-env-sync` больше нет.

**Migration**: Строку `FORGE_DB_HOST_PORT` удалить из `.env` проекта.

### Requirement: Проверка окружения требует хостовый порт целевой БД

**Reason**: Проверять нечего: опубликованного порта нет, а проверку среды выполняет
`forge env check`.

**Migration**: `mise run forge-env-check` — способность `forge-environment-commands`.

### Requirement: Адрес БД внутри сети Compose не зависит от публикации

**Reason**: Сети Compose нет: CLI, шлюз и тесты работают на хосту и обращаются к серверу
по одному адресу.

**Migration**: Адрес сервера задаётся `FORGE_DB_HOST` и `FORGE_DB_PORT`.

### Requirement: Сервер интеграционных тестов не публикуется

**Reason**: Отдельного сервера тестов нет: тестовые базы создаются на общем экземпляре
PostgreSQL workspace.

**Migration**: Изоляция тестов — базы `t_<идентификатор>` и шаблон `t_*` в перечне тестовых БД.

### Requirement: Шаблон окружения содержит корень принятого состояния

**Reason**: Блока forge в `.env.example` kit'а больше нет: корень принятого состояния
репозитория разработки задаёт `mise.toml`.

**Migration**: В репозитории разработки — `FORGE_ACCEPTED_DIR=.forge/db` в `mise.toml`;
в целевом проекте действует значение по умолчанию `db`.

### Requirement: Имена контейнеров forge несут префикс проекта

**Reason**: Контейнеров нет. Изоляция проектов — отдельные базы на общем экземпляре.

**Migration**: Переменная `LBFR_CONTAINER_PREFIX` удаляется из `.env` проекта.

### Requirement: Шаблон окружения содержит префикс контейнеров

**Reason**: Контейнеров и имён контейнеров нет.

**Migration**: Не требуется.

### Requirement: Синхронизация окружения выводит префикс из имени проекта

**Reason**: Цели `make forge-env-sync` и префикса контейнеров нет.

**Migration**: Переменные forge владелец проекта объявляет сам в `mise.toml` и `.env`.

### Requirement: Проверка окружения требует допустимый префикс контейнеров

**Reason**: Префикса контейнеров нет.

**Migration**: Среду проверяет `forge env check`.

### Requirement: Подъём окружения отказывает при занятом имени контейнера

**Reason**: Контейнеров нет, и конфликта имён не возникает.

**Migration**: Не требуется.

### Requirement: Подъём окружения отказывает при занятом хостовом порте

**Reason**: Сервер PostgreSQL общего набора слушает один фиксированный порт, и конфликтов
портов между проектами нет.

**Migration**: Не требуется.

### Requirement: Данные целевой БД хранятся в каталоге проекта

**Reason**: Данные живут в состоянии демона `postgres` workspace, а не в каталоге проекта:
стандарт окружения описывает состояние декларациями демонов.

**Migration**: Каталог `data/lbfr-db` удаляется; данные прежней целевой БД переносятся
клиентом в базу на общем экземпляре — кейс 17 документа кейсов.

### Requirement: Подъём окружения создаёт каталог данных целевой БД

**Reason**: Каталога данных в проекте нет.

**Migration**: Базу при отсутствии создаёт `forge env up`.

### Requirement: Каталог данных целевой БД не попадает в git

**Reason**: Каталога данных в проекте нет.

**Migration**: Запись `/data/lbfr-db/` удалить из `.gitignore` проекта.

## ADDED Requirements

### Requirement: mise — единственный менеджер окружения

В корне репозитория MUST лежать `mise.toml`, а `Makefile`, `docker-compose.yml` и каталог
`docker/` SHALL отсутствовать. Инструменты MUST закрепляться в `mise.toml`: интерпретатор
Python, `uv`, Java и Liquibase. Docker и Docker Compose SHALL NOT использоваться.

#### Scenario: Состав корня

- **WHEN** выполняется `git ls-files Makefile docker-compose.yml docker`
- **THEN** вывод пуст

#### Scenario: Инструменты закреплены

- **WHEN** выполняется `mise install`
- **THEN** установлены закреплённые в `mise.toml` интерпретатор Python, `uv`, Java и Liquibase

#### Scenario: Docker не требуется

- **WHEN** на машине нет Docker
- **THEN** `mise install` и задачи mise выполняются

### Requirement: Задачи окружения — задачи mise

`mise.toml` MUST объявлять задачи `forge-env-up`, `forge-env-check`, `forge` и задачи проверок
`lint`, `format-check`, `types`, `test`. Задачи SHALL быть идемпотентными и вызываемыми
по отдельности; имена задач forge SHALL начинаться с `forge-`, чтобы не перекрывать задачи
общего набора workspace в каскаде mise.

#### Scenario: Перечень задач

- **WHEN** выполняется `mise tasks`
- **THEN** перечислены семь задач с описаниями

#### Scenario: Аргументы передаются

- **WHEN** выполняется `mise run forge -- status --latest`
- **THEN** CLI получает `status --latest`, и код возврата совпадает с кодом CLI

#### Scenario: Каскад не перекрыт

- **WHEN** репозиторий лежит внутри workspace
- **THEN** `mise tasks` показывает и задачи forge, и задачи общего набора — `env-up`, `env-status`

### Requirement: Переменные среды объявлены в mise

Несекретные координаты forge — `FORGE_DB_HOST`, `FORGE_DB_NAME`, `FORGE_ACCEPTED_DIR`,
`FORGE_TEST_DB_HOST`, `FORGE_TEST_DB_ALLOWLIST` — MUST объявляться в секции `[env]` файла
`mise.toml`. Секреты SHALL лежать в `.env`, подключаемом через `_.file`, а шаблон
`.env.example` MUST перечислять имена секретных переменных.

#### Scenario: Несекретные координаты

- **WHEN** выполняется `mise env`
- **THEN** в выводе есть `FORGE_DB_HOST`, `FORGE_DB_NAME`, `FORGE_ACCEPTED_DIR` и `FORGE_TEST_DB_ALLOWLIST`

#### Scenario: Секреты вне git

- **WHEN** выполняется `git check-ignore .env`
- **THEN** путь `.env` игнорируется, а `.env.example` содержит имена `FORGE_DB_PASSWORD` и `FORGE_TEST_DB_PASSWORD` с пустыми значениями

### Requirement: Адрес сервера PostgreSQL берётся из каскада

`FORGE_DB_HOST` и `FORGE_TEST_DB_HOST` по умолчанию SHALL равняться `localhost`; `FORGE_DB_PORT`
и `FORGE_TEST_DB_PORT` — переменной `PG_PORT`, если она задана, иначе `5432`. `FORGE_DB_NAME`
и `FORGE_TEST_DB_ALLOWLIST` SHALL быть заданы явно.

#### Scenario: Внутри workspace

- **WHEN** каскад mise задаёт `PG_PORT=5432`, а порт forge не задан явно
- **THEN** forge подключается к `localhost:5432`

#### Scenario: Вне workspace

- **WHEN** `PG_PORT` не задана, а порт forge не задан явно
- **THEN** forge подключается к `localhost:5432`

#### Scenario: Имя базы не задано

- **WHEN** `FORGE_DB_NAME` не задана
- **THEN** `forge env check` возвращает код `2`, и проверка `database` не пройдена

### Requirement: Целевая база forge — база на общем экземпляре workspace

В репозитории разработки целевая БД операций и тестовые БД MUST жить на общем экземпляре
PostgreSQL workspace — демоне `postgres` корневого `mise.toml`. Собственный сервер БД,
каталог данных и публикация портов SHALL отсутствовать. Изоляция от других проектов —
отдельными базами.

#### Scenario: Общий экземпляр

- **WHEN** демон `postgres` workspace запущен, и выполнены `forge env up` и `forge env check`
- **THEN** все проверки пройдены, а отдельного процесса PostgreSQL forge не запущено

#### Scenario: Изоляция проектов

- **WHEN** forge используется в двух проектах workspace с разными `FORGE_DB_NAME`
- **THEN** накат в одном проекте не меняет базу другого

#### Scenario: Тестовые базы

- **WHEN** выполняется интеграционный тест
- **THEN** он создаёт на общем экземпляре базу с именем `t_<идентификатор>` и удаляет её после себя

### Requirement: Локальные файлы forge не попадают в git

`.gitignore` репозитория MUST исключать `.forge/` — драйвер Liquibase и обмен — и окружение
`.venv/`.

#### Scenario: После подготовки среды

- **WHEN** выполнен `forge env up`
- **THEN** `git status` не показывает файлов `.forge/`

#### Scenario: Файлы проекта рядом остаются в git

- **WHEN** в репозитории разработки закрыта операция forge
- **THEN** `git status` не показывает ни файлов `.forge/`, ни каталога `db/`
