"""Прямой доступ к целевой БД через `psycopg`: журнал Liquibase, объекты схемы, пересоздание."""

from __future__ import annotations

from psycopg import sql

from forge.migration.application.database import JournalEntry
from forge.shared.domain.target_database import TargetDatabase
from forge.shared.infrastructure.postgres import PostgresConnector

# Служебная БД сервера, из-под которой целевая БД удаляется и создаётся заново
MAINTENANCE_DATABASE = "postgres"


class PsycopgJournalReader:
    """Реализация чтения журнала Liquibase."""

    def __init__(self, connector: PostgresConnector) -> None:
        self._connector = connector

    def entries(self, database: TargetDatabase) -> tuple[JournalEntry, ...]:
        with self._connector.connect(database) as connection:
            exists = connection.execute("SELECT to_regclass('public.databasechangelog')").fetchone()
            if exists is None or exists[0] is None:
                return ()
            rows = connection.execute(
                "SELECT id, author, filename, orderexecuted FROM public.databasechangelog "
                "ORDER BY orderexecuted, dateexecuted"
            ).fetchall()
        return tuple(JournalEntry(str(i), str(a), str(f), int(o)) for i, a, f, o in rows)


class PsycopgSchemaProbe:
    """Реализация проверки наличия таблиц и колонок в схеме `public`."""

    def __init__(self, connector: PostgresConnector) -> None:
        self._connector = connector

    def table_exists(self, database: TargetDatabase, table: str) -> bool:
        with self._connector.connect(database) as connection:
            row = connection.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            ).fetchone()
        return row is not None

    def column_exists(self, database: TargetDatabase, table: str, column: str) -> bool:
        with self._connector.connect(database) as connection:
            row = connection.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
                (table, column),
            ).fetchone()
        return row is not None


class PsycopgDatabaseRecreator:
    """Реализация пересоздания целевой БД из-под служебной БД сервера."""

    def __init__(self, connector: PostgresConnector) -> None:
        self._connector = connector

    def recreate(self, database: TargetDatabase) -> None:
        name = sql.Identifier(database.name)
        with self._connector.connect(database, MAINTENANCE_DATABASE) as connection:
            connection.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
            connection.execute(sql.SQL("CREATE DATABASE {}").format(name))
