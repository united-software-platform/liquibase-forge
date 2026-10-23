# Tasks

## 1. Версии действий

- [x] 1.1 `.github/workflows/checks.yml`: `actions/checkout@v4` → `@v7`, `astral-sh/setup-uv@v6` → `@v10.3.2`. Перед шагом установки uv — комментарий: версия точная, потому что с v8 плавающих тегов нет и релизы неизменяемые. Входы `version` и `python-version` не меняются. Проверка: `grep -n "uses:" .github/workflows/checks.yml` показывает новые версии
- [x] 1.2 `.github/workflows/release.yml`: `actions/checkout@v4` → `@v7`. Проверка: `grep -n "checkout@" .github/workflows/*.yml` показывает одну версию в обоих файлах
- [x] 1.3 Убедиться, что версии действий не названы в `CONTRIBUTING.md`, `README.md` и `docs/`. Если названы — обновить. Проверка: `grep -rn "checkout@\|setup-uv@"` вне `.github/` пуст или показывает новые версии

## 2. Тест и локальные проверки

- [x] 2.1 В `tests/release/test_checks_workflow.py` — тест: `checks.yml` и `release.yml` закрепляют одинаковую версию `actions/checkout`, а `astral-sh/setup-uv` закреплён точной версией `vX.Y.Z`. Номера версий в тесте не повторяются. Проверка: тест зелёный; при временной замене на `setup-uv@v10` он падает
- [x] 2.2 Полный локальный прогон раздела «Проверки» `CONTRIBUTING.md`: `ruff check`, `ruff format --check`, `mypy src`, `pytest` с раннером, `tools/make-lint/check.sh`; затем `openspec validate --specs --strict`. Проверка: всё зелёное, число пройденных тестов названо в отчёте
- [x] 2.3 Показать состав коммита и сообщение `LBFR-023: перевести GitHub Actions на Node.js 24` по GIT-016, коммитить после подтверждения. Проверка: рабочее дерево чистое

## 3. Проверка на GitHub

- [x] 3.1 По команде владельца — push ветки `release/v0.3.0` и пробный запуск `gh workflow run release.yml --ref release/v0.3.0 -f bump=patch`. Проверка: job `Проверки` зелёный, в аннотациях прогона нет предупреждения о Node.js 20; job `release` остановлен на шаге «Гейт ветки main» с сообщением «Релиз выпускается только из main»; `VERSION`, теги и релизы не изменились
- [x] 3.2 Записать итог пробного прогона в задачу #12: ссылка на прогон, образ раннера из лога (`ubuntu-latest` → 24.04 или 26.04). Проверка: комментарий в #12 есть

## Workflow follow-up

- Архивировать change в ветке `release/v0.3.0` (`/opsx:archive update-actions-node24`) и отметить задачу 3.1 change `prepare-release-0-3-0`.
- Задача #12 закрывается строкой `Closes #12` в PR выпуска 0.3.0, а не отдельным PR.
