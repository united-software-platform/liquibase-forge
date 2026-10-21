"""Сценарий построения changelog: успех, отказы и ошибки окружения."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.migration.application.generate_changelog.input import GenerateChangelogInput
from forge.migration.application.generate_changelog.output import GenerateChangelogOutput
from forge.migration.application.generate_changelog.use_case import (
    AcceptedModelError,
    GenerateChangelogUseCase,
)
from forge.migration.application.operation_record import (
    OperationRecord,
    OperationRecordUnavailableError,
)
from forge.migration.domain.additive_diff import AdditiveDiff
from forge.migration.domain.changelog import Changelog
from forge.migration.domain.stamp import OperationStamp
from forge.modeling.application.load_model.use_case import LoadModelUseCase
from forge.modeling.application.model_reading import ModelNotFoundError
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader
from tests.migration.models import CUSTOMER, INVOICE

STAMP = OperationStamp("20261017-153000")


class _Operations:
    def __init__(self, available: bool = True) -> None:
        self._available = available

    def read(self, path: str) -> OperationRecord:
        if not self._available:
            raise OperationRecordUnavailableError(f"нет беклога {path}")
        return OperationRecord(STAMP, {1: None, 2: None, 3: None}, "trail")


class _Writer:
    def __init__(self) -> None:
        self.written: dict[str, Changelog] = {}
        self.removed: list[str] = []

    def write(self, path: str, changelog: Changelog) -> None:
        self.written[path] = changelog

    def remove(self, path: str) -> None:
        self.removed.append(path)


def _file(directory: Path, name: str, tables: str) -> str:
    path = directory / name
    body = "tables:\n" + tables if tables else "tables: []\n"
    path.write_text("version: 1\n" + body, encoding="utf-8")
    return str(path)


def _run(
    tmp_path: Path,
    attempt: str | None,
    accepted: str | None = None,
    writer: _Writer | None = None,
    operations: _Operations | None = None,
) -> GenerateChangelogOutput:
    model_path = (
        _file(tmp_path, "model.yaml", attempt)
        if attempt is not None
        else str(tmp_path / "none.yaml")
    )
    accepted_path = (
        _file(tmp_path, "accepted.yaml", accepted)
        if accepted is not None
        else str(tmp_path / "db.yaml")
    )
    use_case = GenerateChangelogUseCase(
        operations or _Operations(),
        LoadModelUseCase(YamlModelDraftReader(), DataModelFactory()),
        writer or _Writer(),
        AdditiveDiff(),
    )
    return use_case.execute(
        GenerateChangelogInput(model_path, accepted_path, "op/tasks.md", "out/changelog.yaml")
    )


def test_first_operation_without_accepted_model(tmp_path: Path) -> None:
    writer = _Writer()

    output = _run(tmp_path, CUSTOMER + INVOICE, writer=writer)

    assert output.generated is True
    assert output.changelog_path == "out/changelog.yaml"
    assert output.logical_file_path == "db/changelog/20261017-153000.yaml"
    assert [(c.id, c.kind, c.table, c.column) for c in output.changesets] == [
        ("20261017-153000-01", "create_table", "customer", None),
        ("20261017-153000-02", "create_table", "invoice", None),
    ]
    assert list(writer.written) == ["out/changelog.yaml"]


def test_new_column(tmp_path: Path) -> None:
    attempt = CUSTOMER.replace(
        "    primary_key", "      - {name: phone, type: text}\n    primary_key"
    )

    output = _run(tmp_path, attempt, accepted=CUSTOMER)

    assert [(c.kind, c.table, c.column) for c in output.changesets] == [
        ("add_column", "customer", "phone")
    ]


def test_same_models_give_empty_changelog(tmp_path: Path) -> None:
    writer = _Writer()

    output = _run(tmp_path, CUSTOMER, accepted=CUSTOMER, writer=writer)

    assert output.generated is True
    assert output.changesets == ()
    assert writer.written["out/changelog.yaml"].changes == ()


def test_non_additive_changes_remove_old_changelog(tmp_path: Path) -> None:
    writer = _Writer()

    output = _run(tmp_path, CUSTOMER, accepted=CUSTOMER + INVOICE, writer=writer)

    assert output.generated is False
    assert output.changelog_path is None
    assert [(c.code, c.table) for c in output.non_additive] == [("table_removed", "invoice")]
    assert writer.written == {}
    assert writer.removed == ["out/changelog.yaml"]


def test_invalid_attempt_model_is_refusal_with_violations(tmp_path: Path) -> None:
    writer = _Writer()

    output = _run(tmp_path, CUSTOMER.replace("type: uuid", "type: varchar"), writer=writer)

    assert output.generated is False
    assert [(v.path, v.code) for v in output.violations] == [
        ("tables[0].columns[0].type", "unknown_type")
    ]
    assert writer.removed == ["out/changelog.yaml"]


def test_missing_attempt_model_is_environment_error(tmp_path: Path) -> None:
    with pytest.raises(ModelNotFoundError):
        _run(tmp_path, None)


def test_invalid_accepted_model_is_environment_error(tmp_path: Path) -> None:
    with pytest.raises(AcceptedModelError):
        _run(tmp_path, CUSTOMER, accepted=CUSTOMER.replace("name: customer", "name: Customer"))


def test_unreadable_accepted_model_is_environment_error(tmp_path: Path) -> None:
    (tmp_path / "accepted.yaml").mkdir()
    use_case = GenerateChangelogUseCase(
        _Operations(),
        LoadModelUseCase(YamlModelDraftReader(), DataModelFactory()),
        _Writer(),
        AdditiveDiff(),
    )

    with pytest.raises(AcceptedModelError):
        use_case.execute(
            GenerateChangelogInput(
                _file(tmp_path, "model.yaml", CUSTOMER),
                str(tmp_path / "accepted.yaml"),
                "op/tasks.md",
                "out/changelog.yaml",
            )
        )


def test_missing_operation_backlog(tmp_path: Path) -> None:
    writer = _Writer()

    with pytest.raises(OperationRecordUnavailableError):
        _run(tmp_path, CUSTOMER, writer=writer, operations=_Operations(available=False))

    assert writer.written == {} and writer.removed == []
