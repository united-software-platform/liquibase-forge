# Цели Liquibase Forge. Через цели шлюза агент без Docker и Liquibase исполняет накат
# и откат changelog: параметров они не принимают — те приходят файлом
# .forge/liquibase-request.json. Цели forge-env-* готовят окружение: дописывают .env,
# проверяют Compose, поднимают БД. Все они терминала не ждут и завершаются сами.
# Блок стоит за определением белого списка любой формы и расширяет его, не трогая литерал.
_FORGE_TARGETS = ("liquibase-update", "liquibase-rollback", "forge-env-sync",
                  "forge-env-check", "forge-env-up")
if "TARGET_VARIABLES" in globals():
    TARGET_VARIABLES.update(dict.fromkeys(_FORGE_TARGETS, frozenset()))
ALLOWED_TARGETS = ALLOWED_TARGETS | frozenset(_FORGE_TARGETS)
