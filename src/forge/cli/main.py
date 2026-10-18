"""Точка входа CLI `forge`.

Разбирает аргументы и передаёт управление команде. Ошибка разбора не печатает справку
`argparse` в стандартный вывод: она становится JSON-объектом ошибки с кодом `2`, чтобы
стандартный вывод любой команды оставался ровно одним JSON-объектом.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import NoReturn

from forge.cli.contract import ExitCode, emit, error_payload


class UsageError(Exception):
    """Ошибка разбора аргументов командной строки."""

    def __init__(self, message: str, usage: str) -> None:
        super().__init__(message)
        self.usage = usage


class _Parser(argparse.ArgumentParser):
    """Парсер, который сообщает об ошибке исключением, а не печатью и выходом."""

    def error(self, message: str) -> NoReturn:
        raise UsageError(message, self.format_usage().strip())


def build_parser() -> argparse.ArgumentParser:
    """Собрать парсер команд. Предметные команды добавляются в последующих изменениях."""
    parser = _Parser(prog="forge", add_help=False)
    parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Выполнить команду и вернуть код возврата."""
    parser = build_parser()
    try:
        parser.parse_args(argv)
    except UsageError as error:
        sys.stderr.write(f"forge: {error}\n")
        emit(error_payload("usage", str(error), usage=error.usage))
        return ExitCode.ENVIRONMENT_ERROR

    # Ни одной команды пока нет: сюда разбор дойти не может
    emit(error_payload("usage", "команда не реализована"))
    return ExitCode.ENVIRONMENT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
