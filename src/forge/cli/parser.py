"""Парсер аргументов CLI: ошибка разбора — исключение, а не печать и выход.

`argparse` по умолчанию печатает справку в стандартный поток ошибок и завершает процесс.
Парсер `forge` вместо этого поднимает `UsageError`: стандартный вывод любой команды остаётся
ровно одним JSON-объектом, а ошибка разбора становится JSON-объектом ошибки с кодом `2`.
"""

from __future__ import annotations

import argparse
from typing import NoReturn


class UsageError(Exception):
    """Ошибка разбора аргументов командной строки."""

    def __init__(self, message: str, usage: str) -> None:
        super().__init__(message)
        self.usage = usage


class Parser(argparse.ArgumentParser):
    """Парсер, который сообщает об ошибке исключением, а не печатью и выходом.

    Вложенные команды создают свои подкоманды тем же классом: ошибка `forge env` без глагола
    уходит туда же, что и ошибка `forge` без команды.
    """

    def error(self, message: str) -> NoReturn:
        raise UsageError(message, self.format_usage().strip())
