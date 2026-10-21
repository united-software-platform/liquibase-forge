"""Сценарий отчёта: файлы для коммита у закрытой операции и их отсутствие у открытой."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.operation.application.build_report.input import BuildReportInput
from forge.operation.application.build_report.output import BuildReportOutput
from forge.operation.application.build_report.use_case import BuildReportUseCase
from forge.operation.domain.factory import OperationFactory
from forge.operation.infrastructure.accepted_state import FileAcceptedState
from forge.operation.infrastructure.attempt_results import JsonAttemptResultsReader
from forge.operation.infrastructure.frontmatter import FrontmatterOperationReadRepository
from tests.operation.backlogs import STAMP, legacy, set_values

ATTEMPT_BACKLOG = "backlog/forge-apply/{stamp}-{number}/tasks.md"


def _report(tmp_path: Path, path: Path) -> BuildReportOutput:
    use_case = BuildReportUseCase(
        FrontmatterOperationReadRepository(tmp_path / "trail"),
        JsonAttemptResultsReader(),
        FileAcceptedState(Path("db")),
        OperationFactory(),
    )
    return use_case.execute(BuildReportInput(str(path)))


def _attempts(path: Path, *verdicts: str) -> None:
    values = {}
    for number, verdict in enumerate(verdicts, start=1):
        values[f"verdict__attempt_{number}"] = verdict
        values[f"backlog__attempt_{number}"] = ATTEMPT_BACKLOG.format(stamp=STAMP, number=number)
    set_values(path, **values)


def test_success_lists_accepted_files_and_trail(tmp_path: Path) -> None:
    path = legacy(tmp_path / "trail")
    _attempts(path, "failure", "success")
    set_values(path, status="success")

    output = _report(tmp_path, path)

    operation = f"{path.parent.as_posix()}/"
    assert output.commit_files == (
        "db/model.yaml",
        f"db/changelog/{STAMP}.yaml",
        "db/changelog/master.yaml",
        operation,
        f"backlog/forge-apply/{STAMP}-1/",
        f"backlog/forge-apply/{STAMP}-2/",
    )


def test_failure_lists_only_trail(tmp_path: Path) -> None:
    path = legacy(tmp_path / "trail")
    _attempts(path, "failure", "failure", "failure")
    set_values(path, status="failure")

    output = _report(tmp_path, path)

    assert output.commit_files == (
        f"{path.parent.as_posix()}/",
        f"backlog/forge-apply/{STAMP}-1/",
        f"backlog/forge-apply/{STAMP}-2/",
        f"backlog/forge-apply/{STAMP}-3/",
    )


@pytest.mark.parametrize("status", ["running", "stopped"])
def test_open_operation_has_no_commit_files(tmp_path: Path, status: str) -> None:
    path = legacy(tmp_path / "trail")
    _attempts(path, "failure")
    set_values(path, status=status)

    assert _report(tmp_path, path).commit_files is None
