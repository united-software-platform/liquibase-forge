"""Общие фикстуры команд CLI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.operation.backlogs import KINDS


@pytest.fixture(params=sorted(KINDS))
def kind(request: pytest.FixtureRequest) -> str:
    """Вид операции, по которому параметризуется тест команды состояния."""
    value: str = request.param
    return value


@pytest.fixture
def backlog(kind: str) -> Callable[..., Path]:
    """Беклог операции вида `kind`: `backlog(root, stamp=STAMP)`."""
    return KINDS[kind]
