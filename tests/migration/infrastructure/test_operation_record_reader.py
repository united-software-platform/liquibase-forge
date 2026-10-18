"""Чтение записи об операции из фронтматтера беклога операции."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.migration.application.operation_record import OperationRecordUnavailableError
from forge.migration.infrastructure.operation_record_reader import (
    FrontmatterOperationRecordReader,
)
from tests.migration.operation_backlog import write_operation


def test_stamp_verdicts_and_attempt_directory(tmp_path: Path) -> None:
    path = write_operation(tmp_path, verdicts=("failure", "success", "null"))

    record = FrontmatterOperationRecordReader().read(str(path))

    assert record.stamp.value == "20261017-153000"
    assert [record.verdict(n) for n in (1, 2, 3)] == ["failure", "success", None]
    assert record.attempt_directory(2) == f"{tmp_path.as_posix()}/attempt-2"


def test_relative_path_gives_relative_attempt_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trail = tmp_path / "backlog" / "forge-model" / "20261017-153000"
    trail.mkdir(parents=True)
    write_operation(trail)
    monkeypatch.chdir(tmp_path)

    record = FrontmatterOperationRecordReader().read("backlog/forge-model/20261017-153000/tasks.md")

    assert record.attempt_directory(1) == "backlog/forge-model/20261017-153000/attempt-1"


def test_missing_backlog(tmp_path: Path) -> None:
    with pytest.raises(OperationRecordUnavailableError):
        FrontmatterOperationRecordReader().read(str(tmp_path / "tasks.md"))


def test_backlog_without_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "tasks.md"
    path.write_text("# Операция\n", encoding="utf-8")

    with pytest.raises(OperationRecordUnavailableError):
        FrontmatterOperationRecordReader().read(str(path))


@pytest.mark.parametrize("subject", ["2026-10-17", "", "20261017-153000-1"])
def test_subject_is_not_stamp(tmp_path: Path, subject: str) -> None:
    path = write_operation(tmp_path, subject=subject)

    with pytest.raises(OperationRecordUnavailableError):
        FrontmatterOperationRecordReader().read(str(path))


def test_unknown_verdict_value(tmp_path: Path) -> None:
    path = write_operation(tmp_path, verdicts=("maybe", "null", "null"))

    with pytest.raises(OperationRecordUnavailableError):
        FrontmatterOperationRecordReader().read(str(path))
