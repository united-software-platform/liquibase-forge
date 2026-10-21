"""Фронтматтер беклога операции: чтение значений и построчная запись статуса.

Фронтматтер — YAML между первыми двумя строками `---`. Запись меняет только строки верхнего
уровня `status:` и `stop_reason:`; остальной текст беклога остаётся побайтово прежним, чтобы
не трогать значения, записанные плагином и исполнением.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from forge.operation.application.operation_reading import (
    OperationRecord,
    OperationUnavailableError,
)
from forge.operation.domain.operation import ATTEMPT_LIMIT, Operation

OPERATION = "forge-model"
OPEN_STATUSES = ("running", "stopped")


def _bounds(lines: list[str], path: str) -> tuple[int, int]:
    found = [index for index, line in enumerate(lines) if line.rstrip("\r\n") == "---"][:2]
    if len(found) < 2:
        raise OperationUnavailableError(f"в беклоге операции {path} нет фронтматтера")
    return found[0], found[1]


def read_frontmatter(path: str) -> dict[str, Any]:
    """Значения фронтматтера беклога."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, UnicodeDecodeError) as error:
        raise OperationUnavailableError(f"беклог операции {path} не прочитать: {error}") from None
    start, end = _bounds(lines, path)
    try:
        data = yaml.safe_load("".join(lines[start + 1 : end]))
    except yaml.YAMLError as error:
        raise OperationUnavailableError(
            f"фронтматтер беклога операции {path} не разбирается: {error}"
        ) from None
    if not isinstance(data, dict):
        raise OperationUnavailableError(f"фронтматтер беклога операции {path} не отображение")
    return data


def _text(path: str, data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise OperationUnavailableError(f"беклог операции {path}: нет значения {key}")
    return value


def _attempts(path: str, data: dict[str, Any], key: str) -> dict[int, str | None]:
    block = data.get(key)
    if block is None:
        return {}
    if not isinstance(block, dict):
        raise OperationUnavailableError(f"беклог операции {path}: {key} не отображение")
    values: dict[int, str | None] = {}
    for number in range(1, ATTEMPT_LIMIT + 1):
        value = block.get(f"attempt_{number}")
        if value is not None and not isinstance(value, str):
            raise OperationUnavailableError(
                f"беклог операции {path}: {key}.attempt_{number} не строка"
            )
        values[number] = value
    return values


class FrontmatterOperationReadRepository:
    """Реализация контракта чтения операций по фронтматтеру беклогов следа."""

    def __init__(self, root: Path, warn: Callable[[str], None] | None = None) -> None:
        self._root = root
        self._warn = warn or (lambda message: sys.stderr.write(f"forge: {message}\n"))

    def get(self, path: str) -> OperationRecord:
        data = read_frontmatter(path)
        stop_reason = data.get("stop_reason")
        if stop_reason is not None and not isinstance(stop_reason, str):
            raise OperationUnavailableError(f"беклог операции {path}: stop_reason не строка")
        trail = _attempts(path, data, "trail")
        parent = PurePosixPath(path).parent
        return OperationRecord(
            path=path,
            stamp=_text(path, data, "subject"),
            intent=_text(path, data, "intent"),
            mode=_text(path, data, "mode"),
            status=_text(path, data, "status"),
            stop_reason=stop_reason,
            verdicts=_attempts(path, data, "verdict"),
            backlogs=_attempts(path, data, "backlog"),
            directories={
                n: trail.get(n) or str(parent / f"attempt-{n}") for n in range(1, ATTEMPT_LIMIT + 1)
            },
        )

    def open_operations(self) -> tuple[str, ...]:
        directory = self._root / OPERATION
        if not directory.is_dir():
            return ()
        found: list[str] = []
        for backlog in sorted(directory.glob("*/tasks.md")):
            path = backlog.as_posix()
            try:
                status = self.get(path).status
            except OperationUnavailableError as error:
                self._warn(f"беклог пропущен: {error}")
                continue
            if status in OPEN_STATUSES:
                found.append(path)
        return tuple(found)


def _scalar(value: str | None) -> str:
    return "null" if value is None else json.dumps(value, ensure_ascii=False)


class FrontmatterOperationWriteRepository:
    """Реализация контракта записи операции: строки `status` и `stop_reason` фронтматтера."""

    def save(self, operation: Operation) -> None:
        path = Path(operation.path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        except (OSError, UnicodeDecodeError) as error:
            raise OperationUnavailableError(
                f"беклог операции {operation.path} не прочитать: {error}"
            ) from None
        start, end = _bounds(lines, operation.path)
        status_line = f"status: {operation.status.value}\n"
        reason_line = f"stop_reason: {_scalar(operation.stop_reason)}\n"
        status_index = reason_index = None
        for index in range(start + 1, end):
            if lines[index].startswith("status:"):
                status_index = index
            elif lines[index].startswith("stop_reason:"):
                reason_index = index
        if status_index is None:
            raise OperationUnavailableError(f"в беклоге операции {operation.path} нет status")
        lines[status_index] = status_line
        if reason_index is not None:
            lines[reason_index] = reason_line
        else:
            lines.insert(status_index + 1, reason_line)
        draft = path.with_name(path.name + ".tmp")
        draft.write_text("".join(lines), encoding="utf-8")
        os.replace(draft, path)
