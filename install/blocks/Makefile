.PHONY: liquibase-update liquibase-rollback forge-env-sync forge-env-check forge-env-up

# Шлюз Liquibase Forge. Цели исполняет раннер по запросу агента: параметры приходят файлом
# .forge/liquibase-request.json, исход уходит файлом .forge/liquibase-result.json. make сводит
# любую ошибку рецепта к коду 2, поэтому истинный код исхода — только в файле результата.
# Логика проверки запроса живёт в скрипте. .env загружается рецептом, а не берётся из окружения
# раннера: учётные данные и перечень тестовых БД действуют сразу после правки .env, без
# перезапуска раннера.
liquibase-update: ## Накат changelog Liquibase по .forge/liquibase-request.json
	@set -a && . ./.env && set +a && python3 tools/liquibase/gateway.py update

liquibase-rollback: ## Откат changeset Liquibase по .forge/liquibase-request.json
	@set -a && . ./.env && set +a && python3 tools/liquibase/gateway.py rollback

# Подготовка окружения Liquibase Forge. Цели входят в белый список раннера: агент выполняет
# их сам, без ручных шагов на хосте.
forge-env-sync: ## Дописать в .env недостающие переменные Liquibase Forge из .env.example
	@sh tools/forge-env/sync-env.sh

forge-env-check: ## Проверить версию Compose (2.20+) и состав сервисов с include:
	@sh tools/forge-env/check.sh

forge-env-up: ## Загрузить и собрать образы, поднять lbfr-db и lbfr-db-test до healthy
	@sh tools/forge-env/up.sh
