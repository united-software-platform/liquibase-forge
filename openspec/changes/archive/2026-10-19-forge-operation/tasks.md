# Tasks

## 1. Общее ядро и Миграция

- [x] 1.1 Перенести `RunnerSettings`, `call_runner`, `runner_settings` и `DEFAULT_TIMEOUT` в `src/forge/shared/infrastructure/runner.py`; перевести `RunnerLiquibaseGateway`, команды и тесты на новые импорты, тесты раннера перенести в `tests/shared/`. Проверка: `grep` не находит старых путей импорта, `uv run pytest` и `uv run mypy src` проходят без правки утверждений
- [x] 1.2 `FrontmatterOperationRecordReader` берёт каталог попытки из `trail.attempt_N`, если блок есть, иначе выводит его по раскладке. Проверка: модульные тесты на беклог с блоком `trail` и без него

## 2. Домен Операции

- [x] 2.1 Реализовать `OperationStatus`, `Attempt`, `Operation` с `stop`, `resume`, `close`, `confirmed_attempt`, `used_attempts`, `CloseOutcome` и ошибки `OperationClosedError`, `OperationNotClosableError`. Проверка: модульные тесты каждого перехода статуса, повторной остановки, закрытия с подтверждённой попыткой, после трёх неудач с подтверждённым и неподтверждённым откатом, преждевременного закрытия, закрытия остановленной операции
- [x] 2.2 Объявить `OperationWriteRepositoryInterface` и `OperationFactory`, восстанавливающую агрегат из `OperationRecord`; неизвестный статус или вердикт — ошибка восстановления. Проверка: модульные тесты восстановления и отказа

## 3. Беклог операции как хранилище

- [x] 3.1 Объявить `OperationReadRepositoryInterface` и `OperationRecord`; реализовать `FrontmatterOperationReadRepository`: запись по пути и перечень открытых операций корня следа (`BACKLOG_ROOT` либо `backlog`), нечитаемые беклоги — предупреждение в stderr. Проверка: модульные тесты на беклогах, порождённых `backlog generate` по шаблонам 1.0.0 и 1.1.0 во временном корне, на беклоге без `trail` и `stop_reason`, на пустом следе и на двух открытых операциях
- [x] 3.2 Реализовать `FrontmatterOperationWriteRepository`: построчная замена `status` и `stop_reason` во фронтматтере, вставка `stop_reason` после `status`, значение — скаляр JSON. Проверка: модульные тесты побайтового совпадения всего, кроме этих строк; причина с кавычками, двоеточием и переводом строки читается обратно; `backlog lint` по изменённому беклогу — код `0`

## 4. Команды `forge stop`, `forge resume`, `forge status`

- [x] 4.1 Реализовать сценарии `StopOperation` и `ResumeOperation` и команды `forge stop --operation --reason`, `forge resume --operation`. Проверка: тесты `tests/cli/test_stop_resume.py` по сценариям требования об остановке и продолжении из `specs/forge-operation-commands/spec.md`
- [x] 4.2 Объявить `EnvironmentProbeInterface`, реализовать `EnvironmentProbe` с проверками `database`, `allowlist`, `runner` и сценарий `GetStatus` для `--operation` и `--latest`; добавить команду `forge status`. Проверка: модульные тесты с подставной проверкой среды на каждый исход и CLI-тесты `tests/cli/test_status.py` по сценариям требований о статусе, проверке среды и ключе `--latest`
- [x] 4.3 Интеграционный тест `EnvironmentProbe` на `lbfr-db-test` и раннере: все проверки пройдены; БД вне перечня; неверный токен раннера. Проверка: тест проходит, а не пропускается

## 5. Команды `forge close` и `forge report`

- [x] 5.1 Объявить `AcceptedStateInterface` и `AttemptResultsReaderInterface`; реализовать `FileAcceptedState` (копирование модели и changelog, `include` в `master.yaml` без повторов) и `JsonAttemptResultsReader`. Проверка: модульные тесты первого и повторного принятия, двух операций подряд, отсутствующих `reconcile.json` и `rollback.json`
- [x] 5.2 Реализовать сценарий `CloseOperation` и команду `forge close --operation`. Проверка: тесты `tests/cli/test_close.py` по сценариям требований о закрытии: принятие в `db/` во временном корне проекта, `failure` без изменения `db/`, преждевременное и повторное закрытие
- [x] 5.3 Реализовать сценарий `BuildReport` и команду `forge report --operation`. Проверка: тесты `tests/cli/test_report.py` на отчёт об успехе на второй попытке, о неудаче с тремя попытками и об остановленной операции с кодами `0`, `1`, `0`
- [x] 5.4 Интеграционный тест через раннер на `lbfr-db-test`: два принятия во временном корне проекта внутри `.forge/`, затем накат принятого `master.yaml` на пустую БД и сверка журнала. Проверка: changeset обеих операций применены в порядке принятия

## 6. Шаблоны и навык

- [x] 6.1 Обновить `templates/forge-model.md` до 1.1.0: блок `trail`, поле `stop_reason`, преамбула с `forge stop` при отказе, непройденном гейте и коде `2`; обновить `templates/forge-apply.md` до 1.1.0: `--operation {{parent}}` в задаче 2.4, та же преамбула. Проверка: `backlog check-template` по обоим шаблонам — расхождений `0`; порождённые беклоги читаются `forge status`
- [x] 6.2 Создать навык `.claude/skills/forge/SKILL.md` по разделу «Навык `forge`» design.md, с проверкой доступности `backlog` первым шагом. Проверка: навык виден в перечне навыков сессии, команды в нём совпадают с контрактом CLI

## 7. Документация

- [x] 7.1 Создать `docs/operation.md` по DOC-014 и DOC-022; обновить контракт команд в `docs/architecture.md` (версия 1.0.4) и добавить раздел «Использование» в `README.md`. Проверка: ссылки относительные, перечень команд в документах совпадает с `forge` без аргументов (ошибка вызова перечисляет подкоманды)

## 8. Итоговая проверка и приёмка

- [x] 8.1 Прогнать `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`, `sh tools/make-lint/check.sh`, `openspec validate forge-operation --type change --strict`. Проверка: все проходят, интеграционные тесты выполнены, а не пропущены
- [x] 8.2 Приёмка: операция через навык `forge` в режиме `auto` на `lbfr-db` с намерением «справочник клиентов» до статуса `success`. Проверка: `backlog verify` беклога операции и беклогов попыток — код `0`; `forge reconcile` без расхождений; `db/model.yaml`, `db/changelog/<штамп>.yaml`, `db/changelog/master.yaml` созданы; отчёт показан владельцу, `db/` не закоммичен без его решения

## Workflow follow-up

- Коммит с кодом `LBFR-009` по подтверждению пользователя; решение владельца о принятом `db/` из приёмки.
- Архивация change и синхронизация спецификаций `forge-operation-commands` и `forge-operation`, затем слияние ветки `forge-operation` в `feature/first-delivery`.
- Задача в репозитории `formular`: плагин 1.3.0 оставляет в беклоге текст выключенного условного блока, если в него вложен другой блок; `check-template` этого не замечает. Шаблоны проекта обходят дефект без вложенных блоков, обход закрепляет `tests/operation/test_templates.py`.
