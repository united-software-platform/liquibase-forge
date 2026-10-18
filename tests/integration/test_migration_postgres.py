"""Прямой доступ к БД на `lbfr-db-test`: журнал Liquibase, объекты схемы, пересоздание БД."""

from __future__ import annotations

import psycopg
import pytest

from forge.migration.application.database import JournalEntry
from forge.migration.infrastructure.postgres import (
    PsycopgDatabaseRecreator,
    PsycopgJournalReader,
    PsycopgSchemaProbe,
)
from forge.shared.application.settings import DatabaseCredentials, DatabaseUnavailableError
from forge.shared.domain.target_database import TargetDatabase
from forge.shared.infrastructure.postgres import PostgresConnector
from tests.conftest import TestDatabase

pytestmark = pytest.mark.integration

JOURNAL = """
CREATE TABLE databasechangelog (
    id varchar(255) NOT NULL, author varchar(255) NOT NULL, filename varchar(255) NOT NULL,
    dateexecuted timestamp NOT NULL, orderexecuted integer NOT NULL
)
"""


def _parts(database: TestDatabase) -> tuple[PostgresConnector, TargetDatabase]:
    connector = PostgresConnector(DatabaseCredentials(database.user, database.password))
    return connector, TargetDatabase(database.host, database.port, database.name)


def test_journal_is_empty_without_table(test_database: TestDatabase) -> None:
    connector, target = _parts(test_database)

    assert PsycopgJournalReader(connector).entries(target) == ()


def test_journal_entries_in_execution_order(test_database: TestDatabase) -> None:
    connector, target = _parts(test_database)
    with psycopg.connect(test_database.conninfo) as connection:
        connection.execute(JOURNAL)
        connection.execute(
            "INSERT INTO databasechangelog VALUES "
            "('b', 'forge', 'db/changelog/2.yaml', now(), 2), "
            "('a', 'forge', 'db/changelog/1.yaml', now(), 1)"
        )

    assert PsycopgJournalReader(connector).entries(target) == (
        JournalEntry("a", "forge", "db/changelog/1.yaml", 1),
        JournalEntry("b", "forge", "db/changelog/2.yaml", 2),
    )


def test_schema_probe(test_database: TestDatabase) -> None:
    connector, target = _parts(test_database)
    probe = PsycopgSchemaProbe(connector)
    with psycopg.connect(test_database.conninfo) as connection:
        connection.execute("CREATE TABLE customer (id integer)")

    assert probe.table_exists(target, "customer")
    assert not probe.table_exists(target, "invoice")
    assert probe.column_exists(target, "customer", "id")
    assert not probe.column_exists(target, "customer", "email")


def test_recreate_gives_empty_database(test_database: TestDatabase) -> None:
    connector, target = _parts(test_database)
    with psycopg.connect(test_database.conninfo) as connection:
        connection.execute("CREATE TABLE customer (id integer)")

    PsycopgDatabaseRecreator(connector).recreate(target)

    assert not PsycopgSchemaProbe(connector).table_exists(target, "customer")


def test_unreachable_database(test_database: TestDatabase) -> None:
    connector, target = _parts(test_database)
    missing = TargetDatabase(target.host, target.port, "forge_missing_database")

    with pytest.raises(DatabaseUnavailableError):
        PsycopgJournalReader(connector).entries(missing)
