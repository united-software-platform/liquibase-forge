"""Сценарий построения changelog: успех, отказы и ошибки окружения."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.migration.application.generate_changelog.input import GenerateChangelogInput
from forge.migration.application.generate_changelog.output import GenerateChangelogOutput
from forge.migration.application.generate_changelog.use_case import (
    AcceptedModelError,
    DropNotAllowedError,
    GenerateChangelogUseCase,
)
from forge.migration.application.operation_record import (
    OperationRecord,
    OperationRecordUnavailableError,
)
from forge.migration.domain.changelog import Changelog
from forge.migration.domain.model_diff import ModelDiff
from forge.migration.domain.stamp import OperationStamp
from forge.migration.infrastructure.liquibase_changelog import LiquibaseConstraintNaming
from forge.modeling.application.load_model.use_case import LoadModelUseCase
from forge.modeling.application.model_reading import ModelNotFoundError
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.domain.foreign_key import ForeignKey
from forge.modeling.domain.identifier import ColumnName, TableName
from forge.modeling.domain.value_list import ValueList
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader
from tests.migration.models import CUSTOMER, INVOICE

STAMP = OperationStamp("20261017-153000")


class _Operations:
    def __init__(
        self, available: bool = True, mode: str | None = None, allow_drop: bool = False
    ) -> None:
        self._available = available
        self._mode = mode
        self._allow_drop = allow_drop

    def read(self, path: str) -> OperationRecord:
        if not self._available:
            raise OperationRecordUnavailableError(f"нет беклога {path}")
        return OperationRecord(
            STAMP,
            {1: None, 2: None, 3: None},
            "trail",
            mode=self._mode,
            allow_drop=self._allow_drop,
        )


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
        ModelDiff(),
        LiquibaseConstraintNaming(),
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


def test_unsupported_changes_remove_old_changelog(tmp_path: Path) -> None:
    writer = _Writer()
    attempt = CUSTOMER.replace("type: string, length: 255", "type: text")

    output = _run(tmp_path, attempt, accepted=CUSTOMER, writer=writer)

    assert output.generated is False
    assert output.changelog_path is None
    assert [(c.code, c.table) for c in output.non_additive] == [("column_type_changed", "customer")]
    assert writer.written == {}
    assert writer.removed == ["out/changelog.yaml"]


WITHOUT_EMAIL = CUSTOMER.replace(
    "      - {name: email, type: string, length: 255, nullable: false}\n", ""
)


def test_dropped_table_and_column_are_changesets(tmp_path: Path) -> None:
    output = _run(tmp_path, WITHOUT_EMAIL, accepted=CUSTOMER + INVOICE)

    assert output.generated is True
    assert output.non_additive == ()
    assert [(c.id, c.kind, c.table, c.column) for c in output.changesets] == [
        ("20261017-153000-01", "drop_table", "invoice", None),
        ("20261017-153000-02", "drop_column", "customer", "email"),
    ]


def test_drop_in_auto_without_consent_is_refused(tmp_path: Path) -> None:
    writer = _Writer()

    with pytest.raises(DropNotAllowedError) as caught:
        _run(
            tmp_path,
            WITHOUT_EMAIL,
            accepted=CUSTOMER + INVOICE,
            writer=writer,
            operations=_Operations(mode="auto", allow_drop=False),
        )

    assert caught.value.objects == ("invoice", "customer.email")
    assert writer.written == {}
    assert writer.removed == ["out/changelog.yaml"]


def test_drop_in_auto_with_consent_is_generated(tmp_path: Path) -> None:
    output = _run(
        tmp_path,
        CUSTOMER,
        accepted=CUSTOMER + INVOICE,
        operations=_Operations(mode="auto", allow_drop=True),
    )

    assert [(c.kind, c.table) for c in output.changesets] == [("drop_table", "invoice")]


def test_drop_in_interactive_needs_no_consent(tmp_path: Path) -> None:
    output = _run(
        tmp_path,
        CUSTOMER,
        accepted=CUSTOMER + INVOICE,
        operations=_Operations(mode="interactive"),
    )

    assert output.generated is True


def test_additions_in_auto_need_no_consent(tmp_path: Path) -> None:
    output = _run(
        tmp_path, CUSTOMER + INVOICE, accepted=CUSTOMER, operations=_Operations(mode="auto")
    )

    assert [(c.kind, c.table) for c in output.changesets] == [("create_table", "invoice")]


def test_model_violations_come_before_consent(tmp_path: Path) -> None:
    output = _run(
        tmp_path,
        CUSTOMER.replace("type: uuid", "type: varchar"),
        accepted=CUSTOMER + INVOICE,
        operations=_Operations(mode="auto"),
    )

    assert output.generated is False
    assert output.violations


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
        ModelDiff(),
        LiquibaseConstraintNaming(),
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


LINKED = INVOICE.replace(
    "    primary_key: [number]",
    "      - {name: customer_id, type: uuid}\n    primary_key: [number]\n"
    "    foreign_keys:\n"
    "      - {columns: [customer_id], references: {table: customer, columns: [id]}}",
)
UNIQUE_EMAIL = CUSTOMER + "    unique:\n      - [email]\n"
UNLINKED = LINKED.split("    foreign_keys:")[0]


def test_constraint_changesets_name_constraint(tmp_path: Path) -> None:
    naming = LiquibaseConstraintNaming()
    output = _run(tmp_path, UNIQUE_EMAIL + LINKED, accepted=CUSTOMER + UNLINKED)
    created = _run(tmp_path, UNIQUE_EMAIL + LINKED)

    assert [(c.kind, c.table, c.column) for c in output.changesets] == [
        ("add_unique", "customer", None),
        ("add_foreign_key", "invoice", None),
    ]
    assert [c.constraint for c in output.changesets] == [
        c.constraint for c in created.changesets if c.kind in ("add_unique", "add_foreign_key")
    ]
    assert all(c.constraint is None for c in created.changesets if c.kind == "create_table")
    assert output.changesets[1].constraint == naming.foreign_key(
        TableName("invoice"),
        ForeignKey((ColumnName("customer_id"),), TableName("customer"), (ColumnName("id"),)),
    )


def test_constraint_drops_in_auto_need_no_consent(tmp_path: Path) -> None:
    output = _run(
        tmp_path,
        CUSTOMER + UNLINKED,
        accepted=UNIQUE_EMAIL + LINKED,
        operations=_Operations(mode="auto", allow_drop=False),
    )

    assert output.generated is True
    assert [(c.kind, c.table) for c in output.changesets] == [
        ("drop_foreign_key", "invoice"),
        ("drop_unique", "customer"),
    ]


EVENT_CHECKED = """
  - name: event
    columns:
      - {name: id, type: bigint, generated: identity}
      - {name: source, type: text, check: [collector, manual]}
    primary_key: [id]
"""


def test_check_changesets_name_constraint_and_column(tmp_path: Path) -> None:
    created = _run(tmp_path, EVENT_CHECKED)
    dropped = _run(
        tmp_path, EVENT_CHECKED.replace(", check: [collector, manual]", ""), EVENT_CHECKED
    )

    expected = LiquibaseConstraintNaming().check(
        TableName("event"), ColumnName("source"), ValueList(("collector", "manual"))
    )
    assert [(c.kind, c.table, c.column, c.constraint) for c in created.changesets] == [
        ("create_table", "event", None, None),
        ("add_check", "event", "source", expected),
    ]
    assert [(c.kind, c.column, c.constraint) for c in dropped.changesets] == [
        ("drop_check", "source", expected)
    ]


def test_generation_change_is_unsupported_change(tmp_path: Path) -> None:
    output = _run(tmp_path, EVENT_CHECKED, EVENT_CHECKED.replace(", generated: identity", ""))

    assert output.generated is False
    assert [(c.code, c.table, c.column) for c in output.non_additive] == [
        ("column_generated_changed", "event", "id")
    ]
