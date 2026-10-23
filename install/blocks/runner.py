        # Цели Liquibase Forge. Через цели шлюза агент без Docker и Liquibase исполняет накат
        # и откат changelog: параметров они не принимают — те приходят файлом
        # .forge/liquibase-request.json. Цели forge-env-* готовят окружение: дописывают .env,
        # проверяют Compose, поднимают БД. Все они терминала не ждут и завершаются сами.
        "liquibase-update",
        "liquibase-rollback",
        "forge-env-sync",
        "forge-env-check",
        "forge-env-up",
