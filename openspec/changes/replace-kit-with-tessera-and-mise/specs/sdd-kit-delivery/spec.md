# Spec Delta

## REMOVED Requirements

### Requirement: Версия поставки закреплена тегом

**Reason**: SDD Developer Kit больше не поставляется в проект: его методология правил и навыков
приходит из плагина tessera, а песочница kit'а — контейнер агента, раннер и Compose — ушла
вместе с ним.

**Migration**: Манифест `.sdd-kit-manifest.json` удаляется из репозитория. Версию плагина
tessera выбирает харнес при установке; норма закрепления инструментов — `ENV-001` плагина.

### Requirement: Состав поставки 1.5.0 присутствует в проекте

**Reason**: Файлы поставки kit'а — `rules/`, `CLAUDE.md`, навык `project-docs` — удаляются из
репозитория: их заменяют правила и навыки плагина tessera.

**Migration**: Навык `project-docs` и правила читаются из установленного в харнесе плагина
tessera; точку входа описывает способность `forge-development-process`.

### Requirement: Проектные отличия в файлах поставки сохраняются

**Reason**: Носители отличий — блоки forge в `Makefile`, `docker-compose.yml`, `.env.example`
и `tools/host-runner/runner.py` kit'а — удаляются: целей `make`, сервиса `claude` и раннера
больше нет, а переменные forge объявлены в `mise.toml` и `.env.example` самого репозитория.

**Migration**: Файлы `Makefile` и `docker-compose.yml` удаляются, `.env.example` остаётся
файтом forge без блока и маркеров, окружение описывает способность `forge-environment`.

### Requirement: Манифест отражает содержимое kit'а, а не проекта

**Reason**: Манифест kit'а удаляется вместе с kit'ом; сверять контрольные суммы файлов поставки
больше не с чем.

**Migration**: Целостность поставляемого плагина сторожат проверки манифестов плагина —
способность `forge-delivery`.

### Requirement: Инструменты SDD развёрнуты после обновления

**Reason**: Цели `make init` и `make openspec-init` исчезают вместе с `Makefile` и контейнером
агента, в котором они исполнялись.

**Migration**: Навыки и команды OpenSpec разворачиваются локально командой `openspec init`
в харнесе разработчика; порядок описывает способность `forge-development-process`.
