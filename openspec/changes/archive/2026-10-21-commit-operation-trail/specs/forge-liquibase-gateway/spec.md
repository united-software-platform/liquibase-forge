# Spec Delta

## ADDED Requirements

### Requirement: Каталог обмена скрыт от git
`forge` при записи файла запроса и шлюз Liquibase при записи файла результата MUST класть
в каталог `.forge/` файл `.gitignore` со строкой `*`, если такого файла там нет. Существующий
`.forge/.gitignore` SHALL NOT перезаписываться. `.gitignore` корня проекта при этом MUST NOT меняться.

#### Scenario: Первый запрос в проекте
- **WHEN** каталога `.forge/` нет, и `forge apply` пишет файл запроса
- **THEN** появляются `.forge/liquibase-request.json` и `.forge/.gitignore` со строкой `*`, а `git status` целевого проекта не показывает файлов `.forge/`

#### Scenario: Шлюз создаёт каталог первым
- **WHEN** каталога `.forge/` нет, и шлюз пишет файл результата
- **THEN** появляются `.forge/liquibase-result.json` и `.forge/.gitignore` со строкой `*`

#### Scenario: Файл уже есть
- **WHEN** в `.forge/.gitignore` владелец записал собственные строки
- **THEN** после запроса и результата содержимое файла не изменилось
