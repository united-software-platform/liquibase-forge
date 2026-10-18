"""Перечень тестовых БД: совпадение, подстановка `*`, пустой перечень, неверная запись."""

from __future__ import annotations

import pytest

from forge.migration.domain.target_database import (
    DatabaseNotAllowedError,
    InvalidAllowlistError,
    TargetDatabase,
    parse_allowlist,
)

ALLOWLIST = "lbfr-db:5432/forge, lbfr-db-test:5432/*"


@pytest.mark.parametrize(
    ("database", "admitted"),
    [
        (TargetDatabase("lbfr-db", 5432, "forge"), True),
        (TargetDatabase("lbfr-db", 5432, "other"), False),
        (TargetDatabase("lbfr-db", 5433, "forge"), False),
        (TargetDatabase("lbfr-db-test", 5432, "t_0001"), True),
        (TargetDatabase("prod-db", 5432, "forge"), False),
    ],
)
def test_admits(database: TargetDatabase, admitted: bool) -> None:
    assert parse_allowlist(ALLOWLIST).admits(database) is admitted


@pytest.mark.parametrize("value", [None, "", " , "])
def test_empty_allowlist_admits_nothing(value: str | None) -> None:
    allowlist = parse_allowlist(value)

    assert allowlist.entries == ()
    assert not allowlist.admits(TargetDatabase("lbfr-db", 5432, "forge"))


@pytest.mark.parametrize(
    "value", ["lbfr-db/forge", "lbfr-db:x/forge", ":5432/forge", "lbfr-db:5432/"]
)
def test_invalid_entry(value: str) -> None:
    with pytest.raises(InvalidAllowlistError):
        parse_allowlist(value)


def test_address_text() -> None:
    assert str(TargetDatabase("lbfr-db", 5432, "forge")) == "lbfr-db:5432/forge"


def test_require_passes_admitted_database() -> None:
    parse_allowlist(ALLOWLIST).require(TargetDatabase("lbfr-db", 5432, "forge"))


@pytest.mark.parametrize(("value", "reason"), [("", "пуст"), (ALLOWLIST, "вне перечня")])
def test_require_refuses(value: str, reason: str) -> None:
    with pytest.raises(DatabaseNotAllowedError, match=reason):
        parse_allowlist(value).require(TargetDatabase("prod-db", 5432, "forge"))
