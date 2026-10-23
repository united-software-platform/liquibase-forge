# Tasks

Выполняется после change `update-actions-node24`: оба правят шаг получения репозитория в `release.yml`.

## 1. Правила защиты в репозитории

- [x] 1.1 `.github/rulesets/main.json` по таблице design.md:
  - `~DEFAULT_BRANCH`, `active`;
  - обход только `DeployKey`;
  - `pull_request` с 0 одобрений;
  - обязательная проверка «Линтер, форматирование, типы, тесты, Makefile» с `integration_id: 15368`, `strict: false`;
  - `non_fast_forward`, `deletion`.

  Проверка: `python3 -m json.tool` разбирает файл
- [x] 1.2 `tools/github/apply-ruleset.sh <файл>`: ищет ruleset по `name`; нет — `POST`, есть — `PUT /rulesets/{id}`. Коды `0`/`1`/`2`, репозиторий берётся из `gh repo view`. Проверка: `sh -n` проходит
- [x] 1.3 `tests/release/test_main_ruleset.py`:
  - контекст обязательной проверки равен `jobs.checks.name` из `checks.yml`;
  - обход только у `DeployKey`;
  - есть `pull_request` (0 одобрений), `non_fast_forward`, `deletion`;
  - скрипт применения с заглушкой `gh`: создаёт, если ruleset'а нет; обновляет по id, если есть; код `1` при ошибке API; код `2` без аргумента.

  Проверка: тесты зелёные; при временной правке имени job'а в `checks.yml` тест контекста падает

## 2. Публикация через ключ развёртывания

- [x] 2.1 `.github/workflows/release.yml`:
  - шаг «Гейт ключа развёртывания» между гейтом ветки и получением репозитория — `RELEASE_DEPLOY_KEY` через `env`, пустой → ошибка с понятным сообщением;
  - `actions/checkout@v7` с `ssh-key: ${{ secrets.RELEASE_DEPLOY_KEY }}`;
  - комментарии в шапке и у шагов: почему ключ, почему релиз остаётся на `GITHUB_TOKEN`.

  Проверка: тест из 2.2
- [x] 2.2 В `tests/release/test_release_workflow.py`:
  - гейт ключа стоит после гейта ветки и до получения репозитория;
  - гейт исполняется через `sh`: пустой ключ → ненулевой код и сообщение, непустой → `0`;
  - `checkout` берёт `ssh-key` из секрета;
  - `git push` в сценарии без `--force`.

  Прежние тесты сценария зелёные. Проверка: `uv run pytest tests/release` зелёный

## 3. Документация

- [x] 3.1 `CONTRIBUTING.md`, «Выпуск версии»:
  - защита `main` (ruleset из `.github/rulesets/main.json`, обход только у deploy key);
  - предусловие «`github-actions[bot]` должен иметь право push» заменено предусловием о ключе и секрете;
  - команды заведения и замены ключа;
  - команда применения ruleset'а с таблицей кодов возврата (DGN-012);
  - выход при сломанном Actions (перевод ruleset'а в `disabled`).

  «Устройство репозитория»: строки для `.github/rulesets/` и `tools/github/`. Строка версии. Проверка: каркас по DGN-008 цел, нормы названы кодами (DGN-010)

## 4. Проверки и коммит

- [x] 4.1 Полный локальный прогон раздела «Проверки» `CONTRIBUTING.md` с раннером и `openspec validate --specs --strict`, валидация change. Проверка: всё зелёное, число тестов названо в отчёте
- [x] 4.2 Показать состав коммита и сообщение `LBFR-020: защитить main обязательными проверками` по GIT-016, коммитить после подтверждения. Проверка: рабочее дерево чистое

## 5. Настройка GitHub (по команде владельца)

- [ ] 5.1 Завести ключ: сгенерировать ключ во временном каталоге, `gh repo deploy-key add --allow-write --title release`, `gh secret set RELEASE_DEPLOY_KEY`, затем удалить временный каталог. Проверка: `gh repo deploy-key list` показывает `release` с записью, `gh secret list` — `RELEASE_DEPLOY_KEY`, файлов ключа на диске нет
- [ ] 5.2 Применить ruleset скриптом `tools/github/apply-ruleset.sh .github/rulesets/main.json`, повторный запуск ничего не меняет. Если форма `bypass_actors` для `DeployKey` не принята — поправить файл и тест (открытый вопрос design.md). Проверка: `gh api repos/{owner}/{repo}/rules/branches/main` перечисляет `pull_request`, `required_status_checks`, `non_fast_forward`, `deletion`
- [ ] 5.3 Проверить критерий на одноразовом PR: ветка с намеренно падающим тестом, PR в `main`, после красного `checks` `gh pr merge --merge` отклоняется. Затем закрыть PR и удалить ветку. Проверка: отказ GitHub записан в отчёт, PR закрыт без слияния, ветки нет

## Workflow follow-up

- Архивировать change в ветке `release/v0.3.0` (`/opsx:archive protect-main-branch`) и отметить задачу 3.2 change `prepare-release-0-3-0`.
- Вторая половина критерия #8 — «сценарий `release` проходит до GitHub Release» — проверяется запуском `release` с `minor` после слияния PR выпуска 0.3.0 через защиту. Если push ключом отклонён: сценарий падает до тега и релиза; поправить ruleset или ключ и запустить снова.
- Задача #8 закрывается строкой `Closes #8` в PR выпуска 0.3.0.
