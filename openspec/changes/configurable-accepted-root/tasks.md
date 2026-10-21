# Tasks

## 1. Настройка корня принятого состояния

- [x] 1.1 Добавить в `EnvironmentSettings` метод `accepted_root()`: `FORGE_ACCEPTED_DIR`, умолчание `db` при незаданном или пустом значении, `SettingsUnavailableError` с именем переменной для абсолютного пути и выхода за корень проекта после нормализации; проверить тестами `tests/shared/infrastructure/test_settings.py` — умолчание, пустое значение, `.forge/db`, `/srv/db`, `../db`, `a/../../db`
- [x] 1.2 Добавить в `EnvironmentProbe` проверку `accepted` с итоговым путём корня в `detail`, непройденную при ошибке настройки; проверить тестами `tests/operation/infrastructure/test_environment_probe.py` и `tests/cli/test_status.py` (сценарии «Корень принятого состояния назван», «Корень вне проекта», «Среда в порядке» с четырьмя проверками)
- [x] 1.3 Обновить таблицу проверок среды в `docs/operation.md`: строка `accepted`, четыре проверки вместо трёх; таблица версий по DOC-022 и DOC-024

## 2. Закрытие и отчёт

- [x] 2.1 Сделать корень обязательным аргументом `FileAcceptedState`, удалить `ACCEPTED_ROOT` из `close.py`, строить корень в `close` и `report` из `settings.accepted_root()`, ошибку настройки переводить в код `2`; проверить тестами `tests/operation/infrastructure/test_accepted_state.py`, `tests/cli/test_close.py`, `tests/cli/test_report.py` (сценарии «Переменная не задана», «Корень вне db», «Абсолютный путь», «Отчёт при корне вне db»)
- [x] 2.2 Перевести описание принятия в `docs/operation.md` и `docs/architecture.md` с безусловного `db/` на корень принятого состояния `FORGE_ACCEPTED_DIR` (по умолчанию `db/`), включая таблицу файлов принятия, строку `forge close` в контракте команд, диаграмму потока и раскладку каталогов; убрать утверждение, что `logicalFilePath` равен физическому пути файла; таблицы версий по DOC-022 и DOC-024

## 3. Построение changelog и откат

- [x] 3.1 Сделать `--accepted` у `forge generate` необязательным с умолчанием `<корень>/model.yaml`, ошибку настройки — код `2` без записи changelog; проверить тестами `tests/cli/test_generate.py` (сценарии «Принятая модель из корня», «Корень принятого состояния некорректен», «Логический путь не зависит от корня»)
- [x] 3.2 Удалить `ACCEPTED_MASTER` из сценария отката и передавать `<корень>/changelog/master.yaml` из `settings.accepted_root()` в `rollback.build_use_case`; проверить тестами `tests/cli/test_rollback.py` и тестами сценария отката (сценарий «Принятое состояние вне db»)
- [x] 3.3 Убрать `--accepted db/model.yaml` из задачи 2.4 `templates/forge-apply.md`, поднять версию шаблона до `1.2.0` с записью в таблицу версий; проверить `backlog check-template` и тем, что `backlog generate --operation forge-apply` порождает беклог без литерала `db/model.yaml`
- [x] 3.4 Обновить описание `forge generate` в `docs/architecture.md` и `docs/migration.md`: `--accepted` необязателен, умолчание — модель корня принятого состояния; таблицы версий по DOC-022 и DOC-024

## 4. Окружение репозитория

- [x] 4.1 Добавить в `.env.example` `FORGE_ACCEPTED_DIR=db` с комментарием о назначении и значении `.forge/db` для репозитория разработки; проверить, что `make forge-env-sync` на `.env` без переменной дописывает её, а заданное значение не меняет
- [x] 4.2 Добавить `/db/` в `.gitignore` с комментарием; проверить, что `git ls-files db` пуст, а созданный вручную `db/model.yaml` не виден в `git status`
- [x] 4.3 Описать в `README.md` переменную `FORGE_ACCEPTED_DIR`: умолчание для целевого проекта, `.forge/db` для репозитория разработки, смену корня в работающем проекте как ручной перенос каталога, ограничение поставки — `.gitignore` и `db/` репозитория разработки в неё не входят
- [x] 4.4 Ввести понятие «Корень принятого состояния (Accepted Root)» в `docs/domain.md` рядом с принятой моделью по TERM-004 и заменить безусловный `db/` в разделе ограничений; таблица версий по DOC-022 и DOC-024

## 5. Интеграционная проверка

- [x] 5.1 Прогнать `uv run pytest`, `uv run ruff check`, `uv run mypy` — все без ошибок
- [x] 5.2 Проверить вручную при `FORGE_ACCEPTED_DIR=.forge/db`: `forge status` называет `.forge/db`, а `forge generate` без `--accepted` на модели с одной таблицей строит changelog с `logicalFilePath` `db/changelog/<штамп>.yaml`; каталог `db/` при этом не появляется
- [x] 5.3 Выполнить `grep -rn -E 'Path\("db"\)|"db/changelog/master.yaml"|--accepted db/' src templates` — совпадений нет

## Workflow follow-up

- Владелец задаёт `FORGE_ACCEPTED_DIR=.forge/db` в `.env` репозитория разработки.
- Коммит с кодом `LBFR-011` — по команде владельца, вместе с удалением `db/` из индекса.
- Архивировать change после ревью.
