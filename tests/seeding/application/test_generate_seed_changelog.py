"""Сценарий построения changelog данных: источники, отказы, удаления и коды."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from forge.migration.application.generate_changelog.use_case import (
    AcceptedModelError,
    DropNotAllowedError,
)
from forge.migration.application.operation_record import (
    OperationRecord,
    OperationRecordUnavailableError,
)
from forge.migration.domain.stamp import OperationStamp
from forge.modeling.application.load_model.use_case import LoadModelUseCase
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader
from forge.seeding.application.generate_seed_changelog.input import GenerateSeedChangelogInput
from forge.seeding.application.generate_seed_changelog.output import (
    DeletedRowView,
    GenerateSeedChangelogOutput,
)
from forge.seeding.application.generate_seed_changelog.use_case import (
    AcceptedSeedError,
    GenerateSeedChangelogUseCase,
)
from forge.seeding.application.seed_reading import SeedUnreadableError
from forge.seeding.domain.data_changelog import DataChangelog
from forge.seeding.domain.factory import SeedFactory
from forge.seeding.domain.seed_diff import SeedDiff
from forge.seeding.infrastructure.yaml_reader import YamlSeedDraftReader
from tests.seeding.support import EXAMPLE_STAMP, MIGRATION_EXAMPLE

OUT = "out/changelog.yaml"


class _Operations:
    def __init__(
        self, available: bool = True, mode: str | None = "interactive", allow_drop: bool = False
    ) -> None:
        self._available = available
        self._mode = mode
        self._allow_drop = allow_drop

    def read(self, path: str) -> OperationRecord:
        if not self._available:
            raise OperationRecordUnavailableError(f"нет беклога {path}")
        return OperationRecord(
            OperationStamp(EXAMPLE_STAMP),
            {1: None, 2: None, 3: None},
            "trail",
            mode=self._mode,
            allow_drop=self._allow_drop,
        )


class _Writer:
    def __init__(self) -> None:
        self.written: dict[str, DataChangelog] = {}
        self.removed: list[str] = []

    def write(self, path: str, changelog: DataChangelog) -> None:
        self.written[path] = changelog

    def remove(self, path: str) -> None:
        self.removed.append(path)


def _example(tmp_path: Path) -> Path:
    """Копия фикстурного примера: модель, принятый seed и seed попытки."""
    for name in ("model.yaml", "accepted.yaml", "attempt.yaml"):
        shutil.copyfile(MIGRATION_EXAMPLE / name, tmp_path / name)
    return tmp_path


def _run(
    directory: Path,
    writer: _Writer | None = None,
    operations: _Operations | None = None,
    seed: str = "attempt.yaml",
    accepted: str = "accepted.yaml",
    model: str = "model.yaml",
    missing_model_as_empty: bool = False,
) -> GenerateSeedChangelogOutput:
    use_case = GenerateSeedChangelogUseCase(
        operations or _Operations(),
        LoadModelUseCase(YamlModelDraftReader(), DataModelFactory()),
        YamlSeedDraftReader(),
        writer or _Writer(),
        SeedFactory(),
        SeedDiff(),
    )
    return use_case.execute(
        GenerateSeedChangelogInput(
            str(directory / seed),
            str(directory / accepted),
            str(directory / model),
            "op/tasks.md",
            OUT,
            missing_model_as_empty,
        )
    )


def test_changelog_is_written_with_changesets_and_deleted_rows(tmp_path: Path) -> None:
    writer = _Writer()

    output = _run(_example(tmp_path), writer)

    assert output.generated is True
    assert output.changelog_path == OUT
    assert output.logical_file_path == f"db/changelog/{EXAMPLE_STAMP}.yaml"
    assert [(c.id, c.kind, c.table, c.rows) for c in output.changesets] == [
        (f"{EXAMPLE_STAMP}-01", "insert_rows", "status_group", 1),
        (f"{EXAMPLE_STAMP}-02", "insert_rows", "order_status", 2),
        (f"{EXAMPLE_STAMP}-03", "update_rows", "order_status", 1),
        (f"{EXAMPLE_STAMP}-04", "delete_rows", "order_status", 1),
    ]
    assert output.deleted_rows == (DeletedRowView("order_status", (("code", "archived"),)),)
    assert list(writer.written) == [OUT]


def test_first_fill_without_accepted_seed_inserts_every_row(tmp_path: Path) -> None:
    output = _run(_example(tmp_path), accepted="none.yaml")

    assert [(c.kind, c.table, c.rows) for c in output.changesets] == [
        ("insert_rows", "status_group", 2),
        ("insert_rows", "order_status", 3),
    ]
    assert output.deleted_rows == ()


def test_attempt_seed_violation_refuses_and_removes_old_changelog(tmp_path: Path) -> None:
    directory = _example(tmp_path)
    (directory / "attempt.yaml").write_text(
        "version: 1\ntables:\n  - name: status_group\n    rows:\n      - {title: Без кода}\n",
        encoding="utf-8",
    )
    writer = _Writer()

    output = _run(directory, writer)

    assert (output.generated, output.changelog_path) == (False, None)
    assert [(v.path, v.code) for v in output.violations] == [
        ("tables[0].rows[0].code", "null_value")
    ]
    assert writer.removed == [OUT] and writer.written == {}


def test_structural_violation_of_attempt_seed_is_reported(tmp_path: Path) -> None:
    directory = _example(tmp_path)
    (directory / "attempt.yaml").write_text("version: 2\ntables: []\n", encoding="utf-8")

    output = _run(directory)

    assert [v.code for v in output.violations] == ["unsupported_version"]


def test_invalid_accepted_seed_is_environment_error(tmp_path: Path) -> None:
    directory = _example(tmp_path)
    (directory / "accepted.yaml").write_text(
        "version: 1\ntables:\n  - name: unknown\n    rows: []\n", encoding="utf-8"
    )

    with pytest.raises(AcceptedSeedError, match="unknown"):
        _run(directory)


def test_unreadable_accepted_seed_is_environment_error(tmp_path: Path) -> None:
    directory = _example(tmp_path)
    (directory / "accepted.yaml").unlink()
    (directory / "accepted.yaml").mkdir()

    with pytest.raises(AcceptedSeedError, match="это каталог"):
        _run(directory)


def test_unreadable_attempt_seed_passes_through(tmp_path: Path) -> None:
    with pytest.raises(SeedUnreadableError):
        _run(_example(tmp_path), seed="none.yaml")


def test_unique_conflict_refuses_with_unsupported(tmp_path: Path) -> None:
    directory = _example(tmp_path)
    attempt = (directory / "accepted.yaml").read_text(encoding="utf-8")
    (directory / "attempt.yaml").write_text(
        attempt.replace("title: Черновик", "title: Архив").replace(
            "title: Архив, fee", "title: Черновик, fee"
        ),
        encoding="utf-8",
    )
    writer = _Writer()

    output = _run(directory, writer)

    assert output.generated is False
    (conflict,) = output.unsupported
    assert (conflict.code, conflict.table, conflict.columns) == (
        "unique_conflict",
        "order_status",
        ("title",),
    )
    assert writer.removed == [OUT]


def test_deletion_in_auto_without_consent_is_refused(tmp_path: Path) -> None:
    writer = _Writer()

    with pytest.raises(DropNotAllowedError) as error:
        _run(_example(tmp_path), writer, _Operations(mode="auto"))

    assert error.value.objects == ("order_status[code=archived]",)
    assert writer.removed == [OUT] and writer.written == {}


def test_deletion_in_auto_with_consent_is_written(tmp_path: Path) -> None:
    output = _run(_example(tmp_path), operations=_Operations(mode="auto", allow_drop=True))

    assert output.generated is True
    assert len(output.deleted_rows) == 1


def test_auto_without_deletions_needs_no_consent(tmp_path: Path) -> None:
    output = _run(_example(tmp_path), operations=_Operations(mode="auto"), accepted="none.yaml")

    assert output.generated is True


def test_invalid_model_is_accepted_model_error(tmp_path: Path) -> None:
    directory = _example(tmp_path)
    (directory / "model.yaml").write_text("version: 1\ntables: 5\n", encoding="utf-8")

    with pytest.raises(AcceptedModelError):
        _run(directory)


def test_missing_default_model_is_empty_and_seed_tables_are_unknown(tmp_path: Path) -> None:
    output = _run(_example(tmp_path), model="none.yaml", missing_model_as_empty=True)

    assert {v.code for v in output.violations} == {"unknown_table"}


def test_operation_unavailable_passes_through(tmp_path: Path) -> None:
    with pytest.raises(OperationRecordUnavailableError):
        _run(_example(tmp_path), operations=_Operations(available=False))
