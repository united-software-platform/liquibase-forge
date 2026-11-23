"""Целевая БД и перечень тестовых БД, на которые разрешены накат и откат."""

from __future__ import annotations

from dataclasses import dataclass


class DatabaseNotAllowedError(Exception):
    """Целевая БД не входит в перечень тестовых: накат и откат запрещены."""


class InvalidAllowlistError(ValueError):
    """Запись перечня тестовых БД не в формате `хост:порт/имя` либо звёздочка стоит не в конце."""


@dataclass(frozen=True)
class TargetDatabase:
    """Адрес БД: хост, порт и имя."""

    host: str
    port: int
    name: str

    def __str__(self) -> str:
        return f"{self.host}:{self.port}/{self.name}"


@dataclass(frozen=True)
class AllowedDatabase:
    """Запись перечня: точное имя БД, префикс имени либо любая БД сервера.

    `name` — точное имя, `prefix` — начало имени для записи вида `t_*`. Обе `None` — любая БД
    сервера, запись `*`.
    """

    host: str
    port: int
    name: str | None
    prefix: str | None = None

    def admits(self, database: TargetDatabase) -> bool:
        if self.host != database.host or self.port != database.port:
            return False
        if self.prefix is not None:
            return database.name.startswith(self.prefix)
        return self.name is None or self.name == database.name


@dataclass(frozen=True)
class TestDatabaseAllowlist:
    """Перечень тестовых БД. Пустой перечень не допускает ни одной БД.

    Команда проверяет адрес до запуска Liquibase: БД вне перечня до шлюза не доходит.
    """

    __test__ = False  # не тестовый класс, несмотря на префикс имени

    entries: tuple[AllowedDatabase, ...]

    def admits(self, database: TargetDatabase) -> bool:
        return any(entry.admits(database) for entry in self.entries)

    def require(self, database: TargetDatabase) -> None:
        """Пропустить БД из перечня; иначе `DatabaseNotAllowedError`."""
        if not self.entries:
            raise DatabaseNotAllowedError(
                "перечень тестовых БД FORGE_TEST_DB_ALLOWLIST пуст: БД не считается тестовой"
            )
        if not self.admits(database):
            raise DatabaseNotAllowedError(f"БД вне перечня тестовых: {database}")


def parse_allowlist(value: str | None) -> TestDatabaseAllowlist:
    """Разобрать `FORGE_TEST_DB_ALLOWLIST`: записи `хост:порт/имя` через запятую.

    В имени записи `*` целиком разрешает любую БД сервера, `t_*` — любую БД, чьё имя начинается
    с префикса: на общем экземпляре PostgreSQL запись `*` открыла бы и базы соседних проектов.
    """
    entries = [entry.strip() for entry in (value or "").split(",") if entry.strip()]
    return TestDatabaseAllowlist(tuple(_entry(entry) for entry in entries))


def _entry(entry: str) -> AllowedDatabase:
    server, slash, name = entry.rpartition("/")
    host, colon, port = server.rpartition(":")
    if not (slash and colon and host and name and port.isdigit()):
        raise InvalidAllowlistError(
            f"запись перечня тестовых БД не в формате хост:порт/имя: {entry}"
        )
    if "*" not in name:
        return AllowedDatabase(host, int(port), name)
    if not name.endswith("*") or "*" in name[:-1]:
        raise InvalidAllowlistError(
            "звёздочка в записи перечня тестовых БД допустима только в конце имени: " + entry
        )
    prefix = name[:-1]
    return AllowedDatabase(host, int(port), None, prefix or None)
