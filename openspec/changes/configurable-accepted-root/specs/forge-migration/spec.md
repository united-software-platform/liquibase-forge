# Spec Delta

## MODIFIED Requirements

### Requirement: Changelog строится из добавляющей разницы моделей
`forge generate --model <модель попытки> [--accepted <принятая модель>] --operation <беклог
операции> --out <путь>` MUST строить changelog только из новых таблиц и новых колонок
существующих таблиц. Без `--accepted` принятой моделью SHALL считаться `<корень>/model.yaml`
корня принятого состояния. Если принятой модели нет, она SHALL считаться пустой.

#### Scenario: Первая операция
- **WHEN** файла `--accepted` нет, а модель попытки содержит две таблицы
- **THEN** команда возвращает код `0`, и changelog содержит по одному changeset на каждую таблицу

#### Scenario: Новая колонка существующей таблицы
- **WHEN** модель попытки добавляет колонку `phone` в таблицу `customer` принятой модели
- **THEN** changelog содержит один changeset добавления колонки `phone` и не трогает остальные объекты

#### Scenario: Модели совпадают
- **WHEN** модель попытки совпадает с принятой
- **THEN** команда возвращает код `0`, и changelog не содержит ни одного changeset

#### Scenario: Принятая модель из корня
- **WHEN** `--accepted` не передан, `FORGE_ACCEPTED_DIR=.forge/db`, а в `.forge/db/model.yaml` есть таблица `customer`
- **THEN** changelog не содержит changeset создания `customer`

#### Scenario: Корень принятого состояния некорректен
- **WHEN** `--accepted` не передан, а `FORGE_ACCEPTED_DIR` — абсолютный путь
- **THEN** команда возвращает код `2`, changelog не записан

### Requirement: Changeset однозначно идентифицирован
Каждый changeset MUST содержать одну таблицу либо одну колонку, иметь `id` вида `<штамп>-<NN>`
с номером по порядку от `01`, `author: forge` и `logicalFilePath` `db/changelog/<штамп>.yaml`
независимо от корня принятого состояния. Штамп SHALL браться из `subject` беклога операции
и соответствовать шаблону `YYYYMMDD-HHMMSS`.

#### Scenario: Идентичность changeset
- **WHEN** беклог операции имеет `subject: "20261017-153000"`, и строятся два changeset
- **THEN** их `id` — `20261017-153000-01` и `20261017-153000-02`, а `logicalFilePath` у обоих `db/changelog/20261017-153000.yaml`

#### Scenario: Штамп не по шаблону
- **WHEN** `subject` беклога операции не соответствует шаблону штампа либо беклога нет
- **THEN** команда возвращает код `2`, changelog не записан

#### Scenario: Логический путь не зависит от корня
- **WHEN** `FORGE_ACCEPTED_DIR=.forge/db`, а беклог операции имеет `subject: "20261017-153000"`
- **THEN** `logicalFilePath` changeset — `db/changelog/20261017-153000.yaml`

### Requirement: Запасной путь пересоздаёт тестовую БД
Если откат Liquibase завершился ошибкой, записи попытки не являются хвостом журнала или
changelog попытки отсутствует, команда MUST пересоздать целевую БД из перечня тестовых через SQL
и накатить принятый `<корень>/changelog/master.yaml` корня принятого состояния, если он есть.
Затем SHALL выполняться та же проверка возврата.

#### Scenario: Хвост журнала не подтверждён
- **WHEN** после записей попытки в журнале есть запись другого changelog
- **THEN** Liquibase rollback не вызывается, БД пересоздана, принятый changelog накатан, `rollback.json` называет запасной путь

#### Scenario: Принятого состояния нет
- **WHEN** запасной путь выполняется, а `<корень>/changelog/master.yaml` отсутствует
- **THEN** БД пересоздана пустой, проверка возврата подтверждена

#### Scenario: Принятое состояние вне db
- **WHEN** запасной путь выполняется, `FORGE_ACCEPTED_DIR=.forge/db`, а `.forge/db/changelog/master.yaml` есть
- **THEN** накатывается `.forge/db/changelog/master.yaml`, а `db/changelog/master.yaml` не читается
