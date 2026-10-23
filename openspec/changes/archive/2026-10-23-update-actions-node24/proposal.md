# Proposal

## Why

При выпуске 0.2.0 прогоны `checks` и `release` предупредили: `actions/checkout@v4` и `astral-sh/setup-uv@v6`
написаны под Node.js 20, который GitHub Actions объявил устаревшим, и раннер уже исполняет их на Node.js 24
принудительно. Пока прогоны зелёные. Но когда Node.js 20 уберут с раннеров, эти действия перестанут
запускаться, а с ними остановятся и проверки PR, и выпуск версии. Задача #12 (LBFR-023) входит в выпуск 0.3.0.

## What Changes

- `.github/workflows/checks.yml`: `actions/checkout@v4` → `actions/checkout@v7`, `astral-sh/setup-uv@v6` → `astral-sh/setup-uv@v10.3.2`.
  Обе версии объявляют `using: node24`.
- `.github/workflows/release.yml`: `actions/checkout@v4` → `actions/checkout@v7`.
- `setup-uv` закрепляется на точном релизе: начиная с v8 Astral не публикует плавающие теги мажорной версии.
- Входы `setup-uv` не меняются. `version: "0.12.7"` и `python-version: "3.12"` в v10.3.2 поддерживаются,
  контрольная сумма uv 0.12.7 ему известна.
- `runs-on: ubuntu-latest` остаётся (решение владельца). Метка переходит на Ubuntu 26.04 с 19 октября
  по 19 ноября 2026 года, но job'ы используют только `sh`, `git`, `gh` и uv, а Python ставит uv,
  а не образ раннера.
- Тест на версии действий: обе workflow закрепляют одну и ту же версию `checkout`, а `setup-uv` закреплён
  на точной версии `X.Y.Z`.

Несовместимых для пользователей forge изменений нет: CLI, поставка и установщик не затронуты.

## Capabilities

### New Capabilities

Нет.

### Modified Capabilities

Нет. Требования `forge-checks` и `forge-release` не меняются: проверки и выпуск ведут себя так же,
меняются только версии действий, которые их исполняют. Поэтому change объявляет `skip_specs: true`.

## Impact

- `.github/workflows/checks.yml`, `.github/workflows/release.yml` — строки `uses:` и комментарий о закреплении `setup-uv`.
- `tests/release/test_checks_workflow.py` или `tests/release/test_release_workflow.py` — тест на версии действий.
- `CONTRIBUTING.md` — по необходимости, если в разделе о workflow названы версии действий (сейчас не названы).
- Внешние зависимости: `actions/checkout` v7, `astral-sh/setup-uv` v10.3.2. Breaking changes setup-uv v8–v10
  нас не задевают. Пользовательский `manifest-file` мы не используем. Автокэш выключается только на
  событиях `pull_request_target`, `workflow_run` и `release`, а у нас `pull_request`, `push`, `workflow_call`.
  `prune-cache: false` влияет только на объём кэша.
- Проверка на GitHub: пробный запуск `release` из ветки `release/v0.3.0` вызывает `checks`
  и останавливается на гейте ветки `main` до любой записи. Для этого ветку нужно отправить на GitHub.
