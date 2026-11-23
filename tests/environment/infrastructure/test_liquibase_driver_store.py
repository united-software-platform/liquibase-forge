"""Хранилище драйвера: загрузка с проверкой суммы, замена повреждённого файла, пара переменных."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from forge.environment.infrastructure.liquibase_driver_store import (
    DEFAULT_DRIVER_SHA256,
    IGNORE_TEXT,
    MAVEN,
    LocalLiquibaseDriverStore,
)
from forge.shared.application.settings import (
    LiquibaseUnavailableError,
    SettingsUnavailableError,
)
from forge.shared.infrastructure.liquibase import driver_path

JAR = b"fake-jar-bytes"
DIGEST = hashlib.sha256(JAR).hexdigest()
WITH_DIGEST = {"FORGE_LIQUIBASE_DRIVER_SHA256": DIGEST}


def _urls(calls: list[str], data: bytes = JAR) -> Callable[[str], bytes]:
    def fetch(url: str) -> bytes:
        calls.append(url)
        return data

    return fetch


def _store(tmp_path, environment, fetch):
    return LocalLiquibaseDriverStore(tmp_path, environment, fetcher=fetch)


def test_default_version_is_pinned_by_digest(tmp_path: Path) -> None:
    """Закреплённая версия проверяется закреплённой суммой: подделка не проходит."""
    urls: list[str] = []
    environment = {"FORGE_LIQUIBASE_DRIVER_VERSION": ""}

    with pytest.raises(LiquibaseUnavailableError, match="не совпала"):
        _store(tmp_path, environment, _urls(urls)).ensure()

    assert urls == [f"{MAVEN}/42.7.13/postgresql-42.7.13.jar"]
    assert not driver_path(tmp_path, {}).exists()


def test_pinned_digest_is_sha256() -> None:
    assert len(DEFAULT_DRIVER_SHA256) == 64
    int(DEFAULT_DRIVER_SHA256, 16)


def test_missing_driver_is_downloaded(tmp_path: Path) -> None:
    urls: list[str] = []

    path = _store(tmp_path, WITH_DIGEST, _urls(urls)).ensure()

    assert path == driver_path(tmp_path, {})
    assert path.read_bytes() == JAR
    assert urls == [f"{MAVEN}/42.7.13/postgresql-42.7.13.jar"]
    assert (tmp_path / ".forge" / ".gitignore").read_text(encoding="utf-8") == IGNORE_TEXT


def test_valid_driver_is_not_downloaded_again(tmp_path: Path) -> None:
    path = driver_path(tmp_path, {})
    path.parent.mkdir(parents=True)
    path.write_bytes(JAR)
    urls: list[str] = []

    assert _store(tmp_path, WITH_DIGEST, _urls(urls)).ensure() == path

    assert urls == []


def test_corrupted_driver_is_replaced(tmp_path: Path) -> None:
    path = driver_path(tmp_path, {})
    path.parent.mkdir(parents=True)
    path.write_bytes(b"broken")

    _store(tmp_path, WITH_DIGEST, _urls([])).ensure()

    assert path.read_bytes() == JAR
    assert [item.name for item in path.parent.iterdir()] == [path.name]


def test_failed_download_leaves_no_file(tmp_path: Path) -> None:
    def fail(url: str) -> bytes:
        raise OSError("network is unreachable")

    with pytest.raises(LiquibaseUnavailableError, match=r"не удалось загрузить.*network"):
        _store(tmp_path, WITH_DIGEST, fail).ensure()

    assert not (tmp_path / ".forge" / "lib").exists()


def test_digest_mismatch_leaves_no_file(tmp_path: Path) -> None:
    with pytest.raises(LiquibaseUnavailableError) as caught:
        _store(tmp_path, WITH_DIGEST, _urls([], b"other-jar")).ensure()

    assert DIGEST in str(caught.value)

    assert not (tmp_path / ".forge" / "lib").exists()


def test_other_version_requires_digest(tmp_path: Path) -> None:
    urls: list[str] = []
    environment = {"FORGE_LIQUIBASE_DRIVER_VERSION": "42.7.14"}

    with pytest.raises(SettingsUnavailableError, match="FORGE_LIQUIBASE_DRIVER_SHA256"):
        _store(tmp_path, environment, _urls(urls)).ensure()

    assert urls == []


def test_other_version_with_digest(tmp_path: Path) -> None:
    urls: list[str] = []
    environment = {"FORGE_LIQUIBASE_DRIVER_VERSION": "42.7.14", **WITH_DIGEST}

    path = _store(tmp_path, environment, _urls(urls)).ensure()

    assert path.name == "postgresql-42.7.14.jar"
    assert urls == [f"{MAVEN}/42.7.14/postgresql-42.7.14.jar"]


def test_digest_is_case_insensitive(tmp_path: Path) -> None:
    environment = {"FORGE_LIQUIBASE_DRIVER_SHA256": DIGEST.upper()}
    path = driver_path(tmp_path, {})
    path.parent.mkdir(parents=True)
    path.write_bytes(JAR)

    assert _store(tmp_path, environment, _urls([])).ensure() == path


@pytest.mark.parametrize(
    ("environment", "name"),
    [
        ({"FORGE_LIQUIBASE_DRIVER_SHA256": "abc"}, "FORGE_LIQUIBASE_DRIVER_SHA256"),
        ({"FORGE_LIQUIBASE_DRIVER_VERSION": "../x"}, "FORGE_LIQUIBASE_DRIVER_VERSION"),
    ],
)
def test_invalid_settings_are_refused_before_download(
    tmp_path: Path, environment: dict[str, str], name: str
) -> None:
    urls: list[str] = []

    with pytest.raises(SettingsUnavailableError, match=name):
        _store(tmp_path, environment, _urls(urls)).ensure()

    assert urls == []


def test_existing_ignore_file_is_kept(tmp_path: Path) -> None:
    ignore = tmp_path / ".forge" / ".gitignore"
    ignore.parent.mkdir()
    ignore.write_text("owner lines\n", encoding="utf-8")

    _store(tmp_path, WITH_DIGEST, _urls([])).ensure()

    assert ignore.read_text(encoding="utf-8") == "owner lines\n"


def test_local_directory_is_hidden_even_when_driver_is_ready(tmp_path: Path) -> None:
    path = driver_path(tmp_path, {})
    path.parent.mkdir(parents=True)
    path.write_bytes(JAR)

    _store(tmp_path, WITH_DIGEST, _urls([])).ensure()

    assert (tmp_path / ".forge" / ".gitignore").read_text(encoding="utf-8") == IGNORE_TEXT
