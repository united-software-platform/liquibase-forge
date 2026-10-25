# Spec Delta

## ADDED Requirements

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
