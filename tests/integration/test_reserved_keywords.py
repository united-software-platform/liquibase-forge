"""Перечень ключевых слов домена совпадает с перечнем сервера PostgreSQL `lbfr-db-test`."""

from __future__ import annotations

import psycopg
import pytest

from forge.modeling.domain.reserved_names import POSTGRESQL_RESERVED_KEYWORDS
from tests.conftest import TestDatabase


@pytest.mark.integration
def test_reserved_keywords_match_server(test_database: TestDatabase) -> None:
    with psycopg.connect(test_database.conninfo) as connection:
        rows = connection.execute(
            "SELECT word FROM pg_get_keywords() WHERE catcode IN ('R', 'T') ORDER BY word"
        ).fetchall()

    assert tuple(word for (word,) in rows) == POSTGRESQL_RESERVED_KEYWORDS
