"""Запись changelog YAML Liquibase: changeset, ключ в порядке модели, типы, повторяемость."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from forge.migration.application.changelog_storage import ChangelogUnreadableError
from forge.migration.domain.additive_diff import AdditiveDiff
from forge.migration.domain.changelog import Changelog
from forge.migration.domain.stamp import OperationStamp
from forge.migration.infrastructure.liquibase_changelog import (
    LiquibaseYamlChangelogReader,
    LiquibaseYamlChangelogWriter,
    liquibase_type,
    render_changelog,
)
from forge.modeling.domain.column_type import parse_column_type
from forge.modeling.domain.data_model import DataModel
from tests.migration.models import CUSTOMER, model

STAMP = OperationStamp("20261017-153000")
LINES = """
  - name: invoice_line
    columns:
      - {name: line_no, type: integer}
      - {name: invoice_id, type: bigint}
      - {name: note, type: string, length: 80}
    primary_key: [invoice_id, line_no]
"""
PHONE = CUSTOMER.replace(
    "    primary_key", "      - {name: phone, type: text, nullable: false}\n    primary_key"
)


def _changelog(accepted: DataModel, attempt: DataModel) -> Changelog:
    return Changelog(STAMP, AdditiveDiff().between(accepted, attempt))


def test_create_table_with_ordered_primary_key() -> None:
    document = yaml.safe_load(render_changelog(_changelog(model(), model(LINES))))

    (entry,) = document["databaseChangeLog"]
    changeset = entry["changeSet"]
    assert (changeset["id"], changeset["author"], changeset["logicalFilePath"]) == (
        "20261017-153000-01",
        "forge",
        "db/changelog/20261017-153000.yaml",
    )
    create, key = changeset["changes"]
    assert create["createTable"]["tableName"] == "invoice_line"
    assert [c["column"] for c in create["createTable"]["columns"]] == [
        {"name": "line_no", "type": "INTEGER", "constraints": {"nullable": False}},
        {"name": "invoice_id", "type": "BIGINT", "constraints": {"nullable": False}},
        {"name": "note", "type": "VARCHAR(80)"},
    ]
    assert key == {
        "addPrimaryKey": {
            "tableName": "invoice_line",
            "columnNames": "invoice_id, line_no",
            "constraintName": "pk_invoice_line",
        }
    }


def test_add_column() -> None:
    document = yaml.safe_load(render_changelog(_changelog(model(CUSTOMER), model(PHONE))))

    (entry,) = document["databaseChangeLog"]
    assert entry["changeSet"]["changes"] == [
        {
            "addColumn": {
                "tableName": "customer",
                "columns": [
                    {
                        "column": {
                            "name": "phone",
                            "type": "TEXT",
                            "constraints": {"nullable": False},
                        }
                    }
                ],
            }
        }
    ]


def test_ids_follow_changes() -> None:
    document = yaml.safe_load(render_changelog(_changelog(model(), model(CUSTOMER + LINES))))

    assert [e["changeSet"]["id"] for e in document["databaseChangeLog"]] == [
        "20261017-153000-01",
        "20261017-153000-02",
    ]


def test_empty_changelog() -> None:
    text = render_changelog(Changelog(STAMP, ()))

    assert yaml.safe_load(text) == {"databaseChangeLog": []}


@pytest.mark.parametrize(
    ("name", "parameters", "expected"),
    [
        ("integer", {}, "INTEGER"),
        ("bigint", {}, "BIGINT"),
        ("boolean", {}, "BOOLEAN"),
        ("string", {"length": 255}, "VARCHAR(255)"),
        ("text", {}, "TEXT"),
        ("decimal", {"precision": 12, "scale": 2}, "NUMERIC(12, 2)"),
        ("date", {}, "DATE"),
        ("timestamp", {}, "TIMESTAMP WITHOUT TIME ZONE"),
        ("timestamp_tz", {}, "TIMESTAMP WITH TIME ZONE"),
        ("uuid", {}, "UUID"),
    ],
)
def test_type_mapping(name: str, parameters: dict[str, int], expected: str) -> None:
    assert liquibase_type(parse_column_type(name, **parameters)) == expected


def test_rendering_is_byte_stable() -> None:
    first = render_changelog(_changelog(model(), model(CUSTOMER + LINES)))
    second = render_changelog(_changelog(model(), model(CUSTOMER + LINES)))

    assert first == second


def test_written_changelog_is_read_back(tmp_path: Path) -> None:
    path = tmp_path / "attempt-1" / "changelog.yaml"
    LiquibaseYamlChangelogWriter().write(
        str(path), _changelog(model(CUSTOMER), model(PHONE + LINES))
    )

    summary = LiquibaseYamlChangelogReader().read(str(path))

    assert summary.logical_file_path == "db/changelog/20261017-153000.yaml"
    assert summary.changeset_ids == ("20261017-153000-01", "20261017-153000-02")
    assert summary.tables == ("invoice_line",)
    assert summary.columns == (("customer", "phone"),)


def test_empty_changelog_summary(tmp_path: Path) -> None:
    path = tmp_path / "changelog.yaml"
    LiquibaseYamlChangelogWriter().write(str(path), Changelog(STAMP, ()))

    summary = LiquibaseYamlChangelogReader().read(str(path))

    assert (summary.logical_file_path, summary.changeset_ids) == (None, ())


def test_remove_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "changelog.yaml"
    path.write_text("x", encoding="utf-8")
    writer = LiquibaseYamlChangelogWriter()

    writer.remove(str(path))
    writer.remove(str(path))

    assert not path.exists()


@pytest.mark.parametrize("text", ["databaseChangeLog: [{changeSet: {}}]\n", "[: x\n", "- 1\n"])
def test_foreign_changelog_is_unreadable(tmp_path: Path, text: str) -> None:
    path = tmp_path / "changelog.yaml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ChangelogUnreadableError):
        LiquibaseYamlChangelogReader().read(str(path))


def test_missing_changelog_is_unreadable(tmp_path: Path) -> None:
    with pytest.raises(ChangelogUnreadableError):
        LiquibaseYamlChangelogReader().read(str(tmp_path / "changelog.yaml"))
