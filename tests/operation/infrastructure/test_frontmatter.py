"""Беклог операции как хранилище: чтение фронтматтера и построчная запись статуса."""

from __future__ import annotations

import difflib
import subprocess
from pathlib import Path

import pytest

from forge.operation.application.operation_reading import OperationUnavailableError
from forge.operation.application.restore import restore
from forge.operation.domain.factory import OperationFactory
from forge.operation.infrastructure.frontmatter import (
    FrontmatterOperationReadRepository,
    FrontmatterOperationWriteRepository,
)
from tests.operation.backlogs import STAMP, backlog_cli, generate, legacy, set_values


def _repository(
    root: Path, warnings: list[str] | None = None
) -> FrontmatterOperationReadRepository:
    return FrontmatterOperationReadRepository(
        root, warn=warnings.append if warnings is not None else None
    )


def test_generated_backlog_is_read(tmp_path: Path) -> None:
    path = generate(tmp_path)

    record = _repository(tmp_path).get(str(path))

    assert (record.stamp, record.mode, record.status, record.stop_reason) == (
        STAMP,
        "auto",
        "running",
        None,
    )
    assert record.intent == "Справочник клиентов: id, email, имя"
    assert record.verdicts == {1: None, 2: None, 3: None}
    assert record.directories[2].endswith(f"{STAMP}/attempt-2")


@pytest.mark.parametrize("consent", [True, False])
def test_consent_is_read_from_generated_backlog(tmp_path: Path, consent: bool) -> None:
    path = generate(tmp_path, allow_drop=consent)

    assert _repository(tmp_path).get(str(path)).allow_drop is consent


def test_legacy_backlog_without_consent_field_reads_false(tmp_path: Path) -> None:
    assert _repository(tmp_path).get(str(legacy(tmp_path))).allow_drop is False


def test_consent_must_be_boolean(tmp_path: Path) -> None:
    path = legacy(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "status: running\n", 'status: running\nallow_drop: "yes"\n'
        ),
        encoding="utf-8",
    )

    with pytest.raises(OperationUnavailableError):
        _repository(tmp_path).get(str(path))


def test_legacy_backlog_without_trail_and_stop_reason(tmp_path: Path) -> None:
    path = legacy(tmp_path)
    set_values(path, verdict__attempt_1="failure")

    record = _repository(tmp_path).get(str(path))

    assert (record.mode, record.stop_reason, record.verdicts[1]) == ("interactive", None, "failure")
    assert record.directories[1] == f"{path.parent.as_posix()}/attempt-1"


def test_trail_block_wins_over_layout(tmp_path: Path) -> None:
    path = legacy(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        "status: running\n", "status: running\ntrail:\n  attempt_1: elsewhere/attempt-1\n"
    )
    path.write_text(text, encoding="utf-8")

    assert _repository(tmp_path).get(str(path)).directories[1] == "elsewhere/attempt-1"


def test_missing_backlog(tmp_path: Path) -> None:
    with pytest.raises(OperationUnavailableError):
        _repository(tmp_path).get(str(tmp_path / "tasks.md"))


def test_open_operations(tmp_path: Path) -> None:
    running = legacy(tmp_path, "20261017-150000")
    closed = legacy(tmp_path, "20261017-160000")
    set_values(closed, status="success")
    broken = tmp_path / "forge-model" / "20261017-170000" / "tasks.md"
    broken.parent.mkdir()
    broken.write_text("без фронтматтера\n", encoding="utf-8")
    warnings: list[str] = []

    found = _repository(tmp_path, warnings).open_operations()

    assert found == (running.as_posix(),)
    assert len(warnings) == 1 and "20261017-170000" in warnings[0]


def test_open_operations_without_trail_root(tmp_path: Path) -> None:
    assert _repository(tmp_path / "backlog").open_operations() == ()


def test_save_changes_only_status_lines(tmp_path: Path) -> None:
    path = generate(tmp_path)
    before = path.read_text(encoding="utf-8")
    operation = restore(_repository(tmp_path).get(str(path)), OperationFactory())
    operation.stop('раннер: "недоступен"\nпосле повтора')

    FrontmatterOperationWriteRepository().save(operation)

    after = path.read_text(encoding="utf-8")
    diff = [
        line
        for line in difflib.ndiff(before.splitlines(), after.splitlines())
        if line.startswith(("+ ", "- "))
    ]
    assert {line[2:].split(":")[0] for line in diff} <= {"status", "stop_reason"}
    assert "+ status: stopped" in diff
    record = _repository(tmp_path).get(str(path))
    assert (record.status, record.stop_reason) == ("stopped", 'раннер: "недоступен"\nпосле повтора')
    lint = subprocess.run([backlog_cli(), "lint", str(path)], capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout + lint.stderr


def test_save_inserts_stop_reason_into_legacy_backlog(tmp_path: Path) -> None:
    path = legacy(tmp_path)
    before = path.read_text(encoding="utf-8").splitlines()
    operation = restore(_repository(tmp_path).get(str(path)), OperationFactory())
    operation.stop("отказ владельца")

    FrontmatterOperationWriteRepository().save(operation)

    after = path.read_text(encoding="utf-8").splitlines()
    index = before.index("status: running")
    assert after[index : index + 2] == ["status: stopped", 'stop_reason: "отказ владельца"']
    assert after[:index] + after[index + 2 :] == before[:index] + before[index + 1 :]


def test_resume_writes_null_reason(tmp_path: Path) -> None:
    path = generate(tmp_path)
    repository = _repository(tmp_path)
    operation = restore(repository.get(str(path)), OperationFactory())
    operation.stop("пауза")
    FrontmatterOperationWriteRepository().save(operation)

    operation.resume()
    FrontmatterOperationWriteRepository().save(operation)

    record = repository.get(str(path))
    assert (record.status, record.stop_reason) == ("running", None)


def _consent(tmp_path: Path, path: Path) -> None:
    operation = restore(_repository(tmp_path).get(str(path)), OperationFactory())
    FrontmatterOperationWriteRepository().save_drop_consent(operation)


def _changed_lines(before: str, after: str) -> list[str]:
    return [
        line
        for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]


def test_consent_replaces_only_its_line(tmp_path: Path) -> None:
    path = generate(tmp_path)
    before = path.read_text(encoding="utf-8")

    _consent(tmp_path, path)

    assert _changed_lines(before, path.read_text(encoding="utf-8")) == [
        "-allow_drop: false",
        "+allow_drop: true",
    ]


def test_consent_is_inserted_after_mode_in_legacy_backlog(tmp_path: Path) -> None:
    path = legacy(tmp_path)
    before = path.read_text(encoding="utf-8")

    _consent(tmp_path, path)

    after = path.read_text(encoding="utf-8")
    assert _changed_lines(before, after) == ["+allow_drop: true"]
    assert "mode: interactive\nallow_drop: true\n" in after


def test_consent_reaches_started_attempt_backlogs(tmp_path: Path) -> None:
    path = generate(tmp_path)
    attempt = tmp_path / "attempt-backlog.md"
    attempt.write_text(
        "---\nmode: auto\nallow_drop: false\nverdict: null\n---\n\n# Попытка 1\n",
        encoding="utf-8",
    )
    set_values(path, backlog__attempt_1=str(attempt))

    _consent(tmp_path, path)

    assert attempt.read_text(encoding="utf-8") == (
        "---\nmode: auto\nallow_drop: true\nverdict: null\n---\n\n# Попытка 1\n"
    )


def test_repeated_consent_changes_nothing(tmp_path: Path) -> None:
    path = generate(tmp_path, allow_drop=True)
    before = path.read_bytes()

    _consent(tmp_path, path)

    assert path.read_bytes() == before
