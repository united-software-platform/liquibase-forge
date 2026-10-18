"""Перечни зарезервированных имён: упорядочены, без повторов, по шаблону идентификатора."""

from __future__ import annotations

import re

import pytest

from forge.modeling.domain.reserved_names import (
    LIQUIBASE_TABLES,
    POSTGRESQL_RESERVED_KEYWORDS,
    POSTGRESQL_SYSTEM_COLUMNS,
)


def test_keywords_are_sorted_and_unique() -> None:
    assert list(POSTGRESQL_RESERVED_KEYWORDS) == sorted(set(POSTGRESQL_RESERVED_KEYWORDS))


@pytest.mark.parametrize(
    "names", [POSTGRESQL_RESERVED_KEYWORDS, POSTGRESQL_SYSTEM_COLUMNS, LIQUIBASE_TABLES]
)
def test_names_are_lowercase_identifiers(names: tuple[str, ...]) -> None:
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in names)
