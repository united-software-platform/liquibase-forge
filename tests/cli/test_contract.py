"""Общий JSON-контракт CLI `forge`: один JSON-объект в stdout, диагностика в stderr."""

from __future__ import annotations

import json

import pytest

from forge.cli.main import main


def _single_json(text: str) -> dict[str, object]:
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 1, f"ожидался ровно один JSON-объект, получено строк: {len(lines)}"
    payload = json.loads(lines[0])
    assert isinstance(payload, dict)
    return payload


@pytest.mark.parametrize(
    ("argv", "description"),
    [
        ([], "без команды"),
        (["unknown"], "неизвестная команда"),
    ],
)
def test_usage_error_is_single_json_with_code_2(
    argv: list[str], description: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(argv)

    captured = capsys.readouterr()
    payload = _single_json(captured.out)
    assert code == 2, description
    error = payload["error"]
    assert isinstance(error, dict)
    assert set(error) == {"kind", "message", "usage"}
    assert error["kind"] == "usage"
    assert error["message"], "сообщение об ошибке непустое"
    assert captured.err.startswith("forge: "), "диагностика уходит в stderr"
