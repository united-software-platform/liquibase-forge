"""Образец интеграционного теста: каждый тест получает свою БД на сервере `lbfr-db-test`."""

from __future__ import annotations

import psycopg
import pytest

from tests.conftest import TestDatabase


@pytest.mark.integration
def test_table_is_created_in_own_database(test_database: TestDatabase) -> None:
    with psycopg.connect(test_database.conninfo) as connection:
        connection.execute("CREATE TABLE sample (id integer PRIMARY KEY)")
        row = connection.execute(
            "SELECT current_database(), to_regclass('public.sample') IS NOT NULL"
        ).fetchone()

    assert row == (test_database.name, True)
