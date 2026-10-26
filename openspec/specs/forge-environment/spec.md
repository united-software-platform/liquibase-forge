# forge-environment Specification

## Purpose

Окружение исполнения Liquibase Forge в Docker Compose: сервисы БД, их адреса внутри сети Compose
и на хосте, переменные окружения и проверки подготовки окружения.

## Requirements

### Requirement: Целевая БД публикуется на хост
Сервис `lbfr-db` MUST публиковать контейнерный порт `5432` на хостовый порт, заданный переменной
`FORGE_DB_HOST_PORT` из `.env`, на всех интерфейсах хоста. Значение порта в `docker-compose.yaml`
SHALL NOT задаваться литералом.

#### Scenario: Подключение с хоста
- **WHEN** в `.env` задано `FORGE_DB_HOST_PORT=11932`, а `lbfr-db` поднят и `healthy`
- **THEN** клиент PostgreSQL на хосте подключается к `localhost:11932` с учётными данными `FORGE_DB_USER` и `FORGE_DB_PASSWORD` и видит БД `FORGE_DB_NAME`

#### Scenario: Подключение с другой машины сети
- **WHEN** хост доступен по сети с другой машины, а сетевой экран хоста не закрывает порт
- **THEN** клиент на другой машине подключается к `<адрес хоста>:${FORGE_DB_HOST_PORT}`

#### Scenario: Смена порта
- **WHEN** пользователь меняет `FORGE_DB_HOST_PORT` в `.env` и пересоздаёт `lbfr-db`
- **THEN** БД публикуется на новом хостовом порту, а прежний порт освобождается

### Requirement: Шаблон окружения содержит хостовый порт целевой БД
`.env.example` MUST содержать `FORGE_DB_HOST_PORT` в блоке целевой БД со значением из диапазона
портов проекта, зафиксированного в документации. Цель `make forge-env-sync` SHALL дописывать
переменную в `.env`, где её нет, не меняя заданное значение.

#### Scenario: Обновление существующей установки
- **WHEN** в `.env` нет `FORGE_DB_HOST_PORT`, и пользователь запускает `make forge-env-sync`
- **THEN** в `.env` дописывается `FORGE_DB_HOST_PORT` со значением из `.env.example`

#### Scenario: Значение уже задано
- **WHEN** в `.env` задано `FORGE_DB_HOST_PORT=15432`, и пользователь запускает `make forge-env-sync`
- **THEN** значение `15432` остаётся без изменений

### Requirement: Проверка окружения требует хостовый порт целевой БД
Цель `make forge-env-check` MUST завершаться с ненулевым кодом и называть `FORGE_DB_HOST_PORT`,
если в итоговой конфигурации Compose у `lbfr-db` нет опубликованного хостового порта.

#### Scenario: Переменная не задана
- **WHEN** в `.env` нет `FORGE_DB_HOST_PORT` либо значение пустое
- **THEN** `make forge-env-check` завершается с ненулевым кодом и сообщает, что нужно выполнить `make forge-env-sync`

#### Scenario: Переменная задана
- **WHEN** в `.env` задано `FORGE_DB_HOST_PORT=11932`, а остальные проверки проходят
- **THEN** `make forge-env-check` завершается с кодом `0` и выводит опубликованный порт `lbfr-db`

### Requirement: Адрес БД внутри сети Compose не зависит от публикации
Агент и шлюз Liquibase MUST обращаться к целевой БД по сети Compose — `FORGE_DB_HOST` и
`FORGE_DB_PORT` (`lbfr-db:5432`), а не по хостовому порту. Публикация порта SHALL NOT менять
перечень `FORGE_TEST_DB_ALLOWLIST`.

#### Scenario: Накат после публикации порта
- **WHEN** порт `lbfr-db` опубликован, а шлюз получает запрос наката на `lbfr-db:5432/forge`
- **THEN** накат проходит так же, как без публикации, перечень тестовых БД не меняется

### Requirement: Сервер интеграционных тестов не публикуется
Сервис `lbfr-db-test` SHALL NOT публиковать порты на хост: он доступен только по сети Compose.

#### Scenario: Конфигурация сервера тестов
- **WHEN** проверяется итоговая конфигурация Compose
- **THEN** у `lbfr-db-test` нет опубликованных портов

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

### Requirement: Репозиторий разработки не хранит след операций
Репозиторий разработки Liquibase Forge MUST NOT содержать след операций в индексе git:
`.gitignore` репозитория SHALL исключать содержимое `backlog/`. В целевом проекте след
коммитится вместе с корнем принятого состояния, и поставка `.gitignore` целевого проекта
MUST NOT менять.

#### Scenario: Проверочный прогон в репозитории разработки
- **WHEN** в репозитории разработки закрыта операция forge
- **THEN** `git status` не показывает файлов `backlog/`

#### Scenario: Чистый индекс
- **WHEN** выполняется `git ls-files backlog`
- **THEN** вывод пуст

### Requirement: Имена контейнеров forge несут префикс проекта
Сервисы `lbfr-db`, `lbfr-db-test` и `lbfr-liquibase` MUST задавать `container_name` вида
`${LBFR_CONTAINER_PREFIX}-<имя сервиса>`. Литерал в `container_name` SHALL NOT использоваться.
Имена сервисов Compose MUST оставаться прежними: адреса внутри сети Compose, `FORGE_DB_HOST`,
`FORGE_TEST_DB_HOST` и `FORGE_TEST_DB_ALLOWLIST` от префикса не зависят.

#### Scenario: Имена контейнеров в итоговой конфигурации
- **WHEN** в `.env` задано `LBFR_CONTAINER_PREFIX=shop`, и проверяется итоговая конфигурация Compose
- **THEN** контейнеры называются `shop-lbfr-db`, `shop-lbfr-db-test` и `shop-lbfr-liquibase`, а сервисы — `lbfr-db`, `lbfr-db-test` и `lbfr-liquibase`

#### Scenario: Два проекта на одном хосте
- **WHEN** окружение forge поднято в проекте с `LBFR_CONTAINER_PREFIX=shop` и `FORGE_DB_HOST_PORT=11932`, а во втором проекте задано `LBFR_CONTAINER_PREFIX=crm` и `FORGE_DB_HOST_PORT=11933`, и в нём запускается `make forge-env-up`
- **THEN** окружение второго проекта поднимается до `healthy`, окружение первого продолжает работать

#### Scenario: Адрес БД внутри сети не меняется
- **WHEN** в `.env` задано `LBFR_CONTAINER_PREFIX=shop`, а шлюз получает запрос наката на `lbfr-db:5432/forge`
- **THEN** накат проходит по адресу `lbfr-db:5432` без правки `FORGE_DB_HOST` и `FORGE_TEST_DB_ALLOWLIST`

### Requirement: Шаблон окружения содержит префикс контейнеров
`.env.example` MUST содержать `LBFR_CONTAINER_PREFIX` с пустым значением и комментарием о том,
что значение различается между проектами на одном хосте и выводится `make forge-env-sync`.
Общее для всех проектов значение по умолчанию SHALL NOT задаваться.

#### Scenario: Шаблон после установки
- **WHEN** forge установлен в проект
- **THEN** блок forge в `.env.example` проекта содержит строку `LBFR_CONTAINER_PREFIX=` с комментарием

### Requirement: Синхронизация окружения выводит префикс из имени проекта
Если в `.env` нет `LBFR_CONTAINER_PREFIX` или значение пустое, `make forge-env-sync` MUST записать
префикс из имени корня проекта: нижний регистр, каждая последовательность символов вне `a-z0-9`
заменена на `-`, `-` по краям отброшены. Заданное непустое значение SHALL NOT меняться. Если префикс
получился пустым, цель MUST завершиться с кодом `1` и попросить задать его вручную.

#### Scenario: Переменной нет
- **WHEN** корень проекта — каталог `My_Shop.v2`, в `.env` нет `LBFR_CONTAINER_PREFIX`, и пользователь запускает `make forge-env-sync`
- **THEN** в `.env` записано `LBFR_CONTAINER_PREFIX=my-shop-v2`, и вывод называет переменную

#### Scenario: Значение пустое
- **WHEN** корень проекта — каталог `shop`, в `.env` есть строка `LBFR_CONTAINER_PREFIX=`, и пользователь запускает `make forge-env-sync`
- **THEN** строка заменена на `LBFR_CONTAINER_PREFIX=shop`, и второй строки с этой переменной в `.env` нет

#### Scenario: Значение уже задано
- **WHEN** в `.env` задано `LBFR_CONTAINER_PREFIX=crm`, и пользователь запускает `make forge-env-sync`
- **THEN** значение `crm` остаётся без изменений

#### Scenario: Из имени каталога префикс не выводится
- **WHEN** корень проекта — каталог `проект`, в `.env` нет `LBFR_CONTAINER_PREFIX`, и пользователь запускает `make forge-env-sync`
- **THEN** цель завершается кодом `1`, сообщает, что `LBFR_CONTAINER_PREFIX` нужно задать вручную, и не записывает переменную

### Requirement: Проверка окружения требует допустимый префикс контейнеров
`make forge-env-check` MUST завершаться с ненулевым кодом и называть `LBFR_CONTAINER_PREFIX`,
если значение пустое или не соответствует `^[a-z0-9][a-z0-9-]*$`. Если значение допустимо,
цель SHALL выводить имя контейнера целевой БД.

#### Scenario: Префикс не задан
- **WHEN** в `.env` нет `LBFR_CONTAINER_PREFIX` либо значение пустое
- **THEN** `make forge-env-check` завершается с ненулевым кодом и сообщает, что нужно выполнить `make forge-env-sync`

#### Scenario: Недопустимый префикс
- **WHEN** в `.env` задано `LBFR_CONTAINER_PREFIX=My Shop`
- **THEN** `make forge-env-check` завершается с ненулевым кодом и называет допустимый вид значения

#### Scenario: Префикс задан
- **WHEN** в `.env` задано `LBFR_CONTAINER_PREFIX=shop`, а остальные проверки проходят
- **THEN** `make forge-env-check` завершается с кодом `0` и выводит имя контейнера `shop-lbfr-db`

### Requirement: Подъём окружения отказывает при занятом имени контейнера
До запуска контейнеров `make forge-env-up` MUST проверять, не принадлежит ли контейнер с именем
контейнера `lbfr-db` или `lbfr-db-test` другому Compose-проекту. Если принадлежит, цель SHALL
завершиться ненулевым кодом, назвать контейнер, каталог проекта-владельца и `LBFR_CONTAINER_PREFIX`,
и SHALL NOT запускать, останавливать или удалять контейнеры.

#### Scenario: Имя занято другим проектом
- **WHEN** контейнер `shop-lbfr-db` принадлежит Compose-проекту в другом каталоге, а в текущем проекте задано `LBFR_CONTAINER_PREFIX=shop`, и пользователь запускает `make forge-env-up`
- **THEN** цель завершается с ненулевым кодом, называет `shop-lbfr-db`, каталог другого проекта и `LBFR_CONTAINER_PREFIX`, а контейнер другого проекта продолжает работать

#### Scenario: Повторный подъём своего окружения
- **WHEN** окружение текущего проекта уже поднято, и пользователь снова запускает `make forge-env-up`
- **THEN** проверка проходит, и цель завершается кодом `0`, как и раньше

### Requirement: Подъём окружения отказывает при занятом хостовом порте
До запуска контейнеров `make forge-env-up` MUST проверять, не опубликован ли хостовый порт `lbfr-db`
контейнером другого Compose-проекта. Если опубликован, цель SHALL завершиться ненулевым кодом,
назвать порт, контейнер-владелец и `FORGE_DB_HOST_PORT`, и SHALL NOT запускать контейнеры.

#### Scenario: Порт занят другим проектом
- **WHEN** порт `11932` опубликован контейнером другого Compose-проекта, а в текущем `.env` задано `FORGE_DB_HOST_PORT=11932`, и пользователь запускает `make forge-env-up`
- **THEN** цель завершается с ненулевым кодом, называет порт `11932`, контейнер-владелец и `FORGE_DB_HOST_PORT`

#### Scenario: Порт занят своим контейнером
- **WHEN** порт `11932` опубликован контейнером `lbfr-db` текущего проекта, и пользователь снова запускает `make forge-env-up`
- **THEN** проверка порта проходит

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
