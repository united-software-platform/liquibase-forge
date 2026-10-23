"""Помощник `environment_missing`: пропуск без признака, ошибка при FORGE_REQUIRE_INTEGRATION=1."""

from __future__ import annotations

import pytest

from tests.conftest import environment_missing

REASON = "FORGE_TEST_DB_HOST не задан: сервер БД интеграционных тестов не настроен"


@pytest.mark.parametrize("value", [None, "", "0"])
def test_skips_without_requirement(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("FORGE_REQUIRE_INTEGRATION", raising=False)
    else:
        monkeypatch.setenv("FORGE_REQUIRE_INTEGRATION", value)

    with pytest.raises(pytest.skip.Exception, match=REASON):
        environment_missing(REASON)


def test_fails_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_REQUIRE_INTEGRATION", "1")

    with pytest.raises(pytest.fail.Exception, match=REASON):
        environment_missing(REASON)
