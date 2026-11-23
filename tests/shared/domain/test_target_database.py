"""Перечень тестовых БД: совпадение, подстановка `*` и префикса, пустой перечень, неверная запись.

Шаблон префикса (`t_*`) изолирует тестовые базы на общем экземпляре PostgreSQL: соседние базы
того же сервера в перечень не попадают.
"""

from __future__ import annotations

import pytest

from forge.shared.domain.target_database import (
    DatabaseNotAllowedError,
    InvalidAllowlistError,
    TargetDatabase,
    parse_allowlist,
)

ALLOWLIST = "localhost:5432/lbfr_forge, localhost:5432/t_*"


@pytest.mark.parametrize(
    ("database", "admitted"),
    [
        (TargetDatabase("localhost", 5432, "lbfr_forge"), True),
        (TargetDatabase("localhost", 5432, "shop"), False),
        (TargetDatabase("localhost", 5433, "lbfr_forge"), False),
        (TargetDatabase("other-host", 5432, "lbfr_forge"), False),
        (TargetDatabase("localhost", 5432, "t_0001"), True),
        (TargetDatabase("localhost", 5432, "t_"), True),
        (TargetDatabase("localhost", 5432, "app_t_0001"), False),
        (TargetDatabase("prod-db", 5432, "lbfr_forge"), False),
    ],
)
def test_admits(database: TargetDatabase, admitted: bool) -> None:
    assert parse_allowlist(ALLOWLIST).admits(database) is admitted


@pytest.mark.parametrize(
    "name",
    ["forge", "t_0001", "shop", "lbfr_forge"],
)
def test_single_star_admits_any_database_of_server(name: str) -> None:
    assert parse_allowlist("localhost:5432/*").admits(TargetDatabase("localhost", 5432, name))


def test_single_star_keeps_server_boundary() -> None:
    assert not parse_allowlist("localhost:5432/*").admits(TargetDatabase("prod-db", 5432, "forge"))


@pytest.mark.parametrize("value", [None, "", " , "])
def test_empty_allowlist_admits_nothing(value: str | None) -> None:
    allowlist = parse_allowlist(value)

    assert allowlist.entries == ()
    assert not allowlist.admits(TargetDatabase("localhost", 5432, "lbfr_forge"))


@pytest.mark.parametrize(
    "value",
    [
        "lbfr-db/forge",
        "other-db:x/forge",
        ":5432/forge",
        "other-db:5432/",
        "localhost:5432/t_*_x",
        "localhost:5432/*x",
        "localhost:5432/t**",
    ],
)
def test_invalid_entry(value: str) -> None:
    with pytest.raises(InvalidAllowlistError):
        parse_allowlist(value)


def test_star_not_at_end_names_the_entry() -> None:
    with pytest.raises(InvalidAllowlistError, match="localhost:5432/t_\\*_x"):
        parse_allowlist("localhost:5432/t_*_x")


def test_address_text() -> None:
    assert str(TargetDatabase("localhost", 5432, "forge")) == "localhost:5432/forge"


def test_require_passes_admitted_database() -> None:
    parse_allowlist(ALLOWLIST).require(TargetDatabase("localhost", 5432, "lbfr_forge"))
    parse_allowlist(ALLOWLIST).require(TargetDatabase("localhost", 5432, "t_0001"))


@pytest.mark.parametrize(("value", "reason"), [("", "пуст"), (ALLOWLIST, "вне перечня")])
def test_require_refuses(value: str, reason: str) -> None:
    with pytest.raises(DatabaseNotAllowedError, match=reason):
        parse_allowlist(value).require(TargetDatabase("prod-db", 5432, "forge"))


def test_require_refuses_database_outside_prefix() -> None:
    with pytest.raises(DatabaseNotAllowedError, match="вне перечня"):
        parse_allowlist(ALLOWLIST).require(TargetDatabase("localhost", 5432, "shop"))
