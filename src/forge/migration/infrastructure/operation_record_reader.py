"""Чтение записи об операции из фронтматтера беклога операции.

Anti-Corruption Layer к беклогу контекста Операция: из фронтматтера берутся только
`subject` и `verdict.attempt_N`, каталог следа — каталог беклога по раскладке следа.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

import yaml

from forge.migration.application.operation_record import (
    OperationRecord,
    OperationRecordUnavailableError,
)
from forge.migration.domain.stamp import InvalidStampError, OperationStamp

ATTEMPTS = (1, 2, 3)
_VERDICTS = ("success", "failure", None)


class FrontmatterOperationRecordReader:
    """Реализация контракта чтения записи об операции по фронтматтеру YAML."""

    def read(self, path: str) -> OperationRecord:
        try:
            with open(path, encoding="utf-8") as file:
                text = file.read()
        except (OSError, UnicodeDecodeError) as error:
            raise OperationRecordUnavailableError(
                f"беклог операции {path} не прочитать: {error}"
            ) from None
        frontmatter = _frontmatter(path, text)
        try:
            stamp = OperationStamp(str(frontmatter.get("subject", "")))
        except InvalidStampError as error:
            raise OperationRecordUnavailableError(f"беклог операции {path}: {error}") from None
        return OperationRecord(
            stamp=stamp,
            verdicts={attempt: _verdict(path, frontmatter, attempt) for attempt in ATTEMPTS},
            trail_directory=str(PurePosixPath(path).parent),
        )


def _frontmatter(path: str, text: str) -> dict[str, Any]:
    lines = text.splitlines()
    bounds = [index for index, line in enumerate(lines) if line.strip() == "---"][:2]
    if len(bounds) < 2:
        raise OperationRecordUnavailableError(f"в беклоге операции {path} нет фронтматтера")
    try:
        data = yaml.safe_load("\n".join(lines[bounds[0] + 1 : bounds[1]]))
    except yaml.YAMLError as error:
        raise OperationRecordUnavailableError(
            f"фронтматтер беклога операции {path} не разбирается: {error}"
        ) from None
    if not isinstance(data, dict):
        raise OperationRecordUnavailableError(
            f"фронтматтер беклога операции {path} не является отображением"
        )
    return data


def _verdict(path: str, frontmatter: dict[str, Any], attempt: int) -> str | None:
    verdicts = frontmatter.get("verdict")
    value = verdicts.get(f"attempt_{attempt}") if isinstance(verdicts, dict) else None
    if value not in _VERDICTS:
        raise OperationRecordUnavailableError(
            f"беклог операции {path}: verdict.attempt_{attempt} должен быть success, failure "
            f"или null, получено {value!r}"
        )
    return value
