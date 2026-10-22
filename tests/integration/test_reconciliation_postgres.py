"""Интроспекция каталога и журнала Liquibase на `lbfr-db-test`."""

from __future__ import annotations

import psycopg
import pytest

from forge.modeling.domain.column_type import parse_column_type
from forge.reconciliation.domain.actual_schema import ActualForeignKey
from forge.reconciliation.domain.journal_check import JournalRecord
from forge.reconciliation.infrastructure.postgres_introspection import (
    PsycopgJournalRecordsReader,
    PsycopgSchemaIntrospector,
)
from forge.shared.application.settings import DatabaseCredentials
from forge.shared.domain.target_database import TargetDatabase
from forge.shared.infrastructure.postgres import PostgresConnector
from tests.conftest import TestDatabase

pytestmark = pytest.mark.integration


def _parts(database: TestDatabase) -> tuple[PostgresConnector, TargetDatabase]:
    connector = PostgresConnector(DatabaseCredentials(database.user, database.password))
    return connector, TargetDatabase(database.host, database.port, database.name)


def test_types_nullability_and_keys(test_database: TestDatabase) -> None:
    connector, target = _parts(test_database)
    with psycopg.connect(test_database.conninfo) as connection:
        connection.execute(
            "CREATE TABLE sample ("
            " a integer NOT NULL, b bigint, c boolean, d varchar(80), e text,"
            " f numeric(12,2), g date, h timestamp, i timestamptz, j uuid NOT NULL,"
            " k smallint, l varchar, m numeric,"
            " CONSTRAINT any_name PRIMARY KEY (j, a))"
        )
        connection.execute("CREATE TABLE no_key (id integer)")
        connection.execute("CREATE TABLE databasechangelog (id text)")
        connection.execute("CREATE TABLE databasechangeloglock (id integer)")
        connection.execute("CREATE VIEW sample_view AS SELECT a FROM sample")

    actual = PsycopgSchemaIntrospector(connector).read(target)

    assert [t.name for t in actual.tables] == ["no_key", "sample"]
    sample = actual.table("sample")
    assert sample is not None
    assert sample.primary_key == ("j", "a")
    types = {c.name: (c.type, c.database_type, c.nullable) for c in sample.columns}
    assert types["a"] == (parse_column_type("integer"), "integer", False)
    assert types["d"][0] == parse_column_type("string", length=80)
    assert types["f"][0] == parse_column_type("decimal", precision=12, scale=2)
    assert types["h"][0] == parse_column_type("timestamp")
    assert types["i"][0] == parse_column_type("timestamp_tz")
    assert types["j"] == (parse_column_type("uuid"), "uuid", False)
    assert types["k"] == (None, "smallint", True)
    assert types["l"] == (None, "character varying", True)
    assert types["m"] == (None, "numeric", True)
    assert [c.name for c in sample.columns] == list("abcdefghijklm")
    no_key = actual.table("no_key")
    assert no_key is not None and no_key.primary_key is None


def test_journal_without_table(test_database: TestDatabase) -> None:
    connector, target = _parts(test_database)

    assert PsycopgJournalRecordsReader(connector).records(target) == ()


def test_journal_records(test_database: TestDatabase) -> None:
    connector, target = _parts(test_database)
    with psycopg.connect(test_database.conninfo) as connection:
        connection.execute(
            "CREATE TABLE databasechangelog (id text, author text, filename text,"
            " dateexecuted timestamp, orderexecuted integer, exectype text)"
        )
        connection.execute(
            "INSERT INTO databasechangelog VALUES"
            " ('b', 'forge', 'f.yaml', now(), 2, 'MARK_RAN'),"
            " ('a', 'forge', 'f.yaml', now(), 1, 'EXECUTED')"
        )

    assert PsycopgJournalRecordsReader(connector).records(target) == (
        JournalRecord("a", "forge", "f.yaml", "EXECUTED"),
        JournalRecord("b", "forge", "f.yaml", "MARK_RAN"),
    )


def test_foreign_keys_and_unique_constraints(test_database: TestDatabase) -> None:
    connector, target = _parts(test_database)
    with psycopg.connect(test_database.conninfo) as connection:
        connection.execute(
            "CREATE TABLE line (invoice_id bigint, line_no integer, code text, tenant integer,"
            " CONSTRAINT line_pk PRIMARY KEY (invoice_id, line_no),"
            " CONSTRAINT line_code UNIQUE (tenant, code))"
        )
        connection.execute(
            "CREATE TABLE payment (id bigint PRIMARY KEY, l integer, i bigint, parent_id bigint,"
            " CONSTRAINT any_fk FOREIGN KEY (l, i) REFERENCES line (line_no, invoice_id),"
            " CONSTRAINT self_fk FOREIGN KEY (parent_id) REFERENCES payment (id))"
        )
        connection.execute("CREATE UNIQUE INDEX lonely_index ON payment (l)")

    actual = PsycopgSchemaIntrospector(connector).read(target)

    line, payment = actual.table("line"), actual.table("payment")
    assert line is not None and payment is not None
    assert (line.unique, line.foreign_keys) == ((("tenant", "code"),), ())
    # Уникальный индекс без ограничения не читается
    assert payment.unique == ()
    assert set(payment.foreign_keys) == {
        ActualForeignKey(("l", "i"), "line", ("line_no", "invoice_id")),
        ActualForeignKey(("parent_id",), "payment", ("id",)),
    }
