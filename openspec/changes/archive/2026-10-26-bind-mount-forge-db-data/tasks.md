# Tasks

## 1. Монтирование данных lbfr-db из каталога проекта

- [x] 1.1 В `docker/lbfr/docker-compose.yaml` заменить у `lbfr-db` монтирование `lbfr-db-data:/var/lib/postgresql/data` на `./data/lbfr-db:/var/lib/postgresql/data`, удалить секцию `volumes:` верхнего уровня с томом `lbfr-db-data`, дополнить комментарий шапки файла (путь от корня проекта, владелец данных — пользователь контейнера); проверить: `docker compose config --format json lbfr-db` показывает bind `<корень>/data/lbfr-db`, `lbfr-db-test` остаётся на `tmpfs`
- [x] 1.2 В `tests/tools/test_forge_env.py` добавить тесты по разобранному `COMPOSE_FILE`: у `lbfr-db` монтирование `./data/lbfr-db:/var/lib/postgresql/data`, тома `lbfr-db-data` в `volumes` верхнего уровня нет, у `lbfr-db-test` `tmpfs` на `/var/lib/postgresql/data`; проверить: `uv run pytest tests/tools/test_forge_env.py` зелёный

## 2. Создание каталога в make forge-env-up

- [x] 2.1 В `tools/forge-env/up.sh` после `preflight.sh` и до `docker compose up` добавить `mkdir -p data/lbfr-db` с комментарием, зачем каталог создаётся не демоном; проверить: `sh tools/forge-env/up.sh` в окружении-заглушке создаёт `data/lbfr-db`
- [x] 2.2 В `tests/tools/test_forge_env.py` добавить тесты: `up.sh` создаёт `data/lbfr-db` во временном каталоге, не трогает существующий файл в `data/`, не создаёт каталог при отказе `preflight.sh`; проверить: `uv run pytest tests/tools/test_forge_env.py` зелёный

## 3. Исключение каталога из git

- [x] 3.1 Дописать строку `/data/lbfr-db/` с комментарием в блок forge `.gitignore` и тем же текстом в `install/blocks/gitignore`; проверить: `uv run pytest tests/delivery` зелёный, `git check-ignore data/lbfr-db/PG_VERSION` выводит путь, `git check-ignore data/other.csv` ничего не выводит

## 4. Документ кейсов

- [x] 4.1 В `docs/use-cases.md` перевести кейс 2 («данные тома `lbfr-db-data` сохраняются») на каталог `data/lbfr-db`; проверить чтением: упоминаний тома в кейсе нет
- [x] 4.2 В кейсе 12 заменить поиск и удаление тома `<проект>_lbfr-db-data` удалением `data/lbfr-db` одноразовым контейнером образа `LBFR_POSTGRES_IMAGE` (каталог принадлежит пользователю контейнера), строку `.gitignore` из блока убирает удаление блока; проверить: команда из кейса удаляет наполненный `data/lbfr-db` на хосте
- [x] 4.3 В кейсе 14 убрать фразу о новом пустом томе второго проекта: данные каждого проекта лежат в его каталоге и от `COMPOSE_PROJECT_NAME` не зависят; проверить чтением
- [x] 4.4 Добавить кейс «Хочу перенести данные целевой БД из тома в каталог проекта» по [DGN-006](../../../rules/project-docs-rules.md#каркас-кейса-dgn-006) — когда: обновил forge, `lbfr-db` поднялся пустым; что делаю: останавливаю `lbfr-db`, копирую `<проект>_lbfr-db-data` в `data/lbfr-db` одноразовым контейнером (`cp -a /from/. /to/`), поднимаю `make forge-env-up`, проверяю данные, удаляю том; что получаю; если не вышло — накат принятого состояния из `db/` заново. Номер — следующий свободный по DGN-007; проверить: сценарий кейса проходит на томе с таблицей, данные видны после подъёма

## 5. Интеграционная проверка

- [x] 5.1 На хосте: `make forge-env-up` в чистом проекте — появляется `data/lbfr-db`, `lbfr-db` `healthy`; создать таблицу, пересоздать контейнер `docker compose up -d --force-recreate lbfr-db` — таблица на месте; `git status` не показывает `data/lbfr-db`
- [x] 5.2 Прогнать полный набор проверок `CONTRIBUTING.md` при наполненном `data/lbfr-db`: `uv run pytest` (с интеграционными тестами наката и отката через `lbfr-liquibase`, монтирующий весь проект), `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`, `sh tools/make-lint/check.sh` — все зелёные

## Workflow follow-up

- Коммиты в ветке `feature/lbfr-030` с заголовком `LBFR-030: …` по GIT-009 — по явному запросу.
- После зелёного прогона группы 5 закрыть issue #24 (LBFR-030) комментарием с итогом прогона.
- Архивировать изменение `bind-mount-forge-db-data` после ревью.
