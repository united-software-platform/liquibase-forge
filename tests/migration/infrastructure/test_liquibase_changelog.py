"""Запись changelog YAML Liquibase: changeset, ключ в порядке модели, типы, повторяемость."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from forge.migration.application.changelog_storage import ChangelogUnreadableError, ConstraintRef
from forge.migration.domain.changelog import Changelog
from forge.migration.domain.model_diff import ModelDiff
from forge.migration.domain.stamp import OperationStamp
from forge.migration.infrastructure.liquibase_changelog import (
    LiquibaseYamlChangelogReader,
    LiquibaseYamlChangelogWriter,
    foreign_key_name,
    liquibase_type,
    render_changelog,
    unique_name,
)
from forge.modeling.domain.column_type import parse_column_type
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.foreign_key import ForeignKey
from forge.modeling.domain.identifier import ColumnName, TableName
from forge.modeling.domain.unique_set import UniqueSet
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
    return Changelog(STAMP, ModelDiff().between(accepted, attempt))


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


def test_drop_column_is_rendered_exactly_with_rollback() -> None:
    text = render_changelog(_changelog(model(PHONE), model(CUSTOMER)))

    assert text == (
        "# Changelog операции 20261017-153000: построен forge generate, вручную не правится\n"
        "databaseChangeLog:\n"
        "- changeSet:\n"
        "    id: 20261017-153000-01\n"
        "    author: forge\n"
        "    logicalFilePath: db/changelog/20261017-153000.yaml\n"
        "    changes:\n"
        "    - dropColumn:\n"
        "        tableName: customer\n"
        "        columnName: phone\n"
        "    rollback:\n"
        "    - addColumn:\n"
        "        tableName: customer\n"
        "        columns:\n"
        "        - column:\n"
        "            name: phone\n"
        "            type: TEXT\n"
        "            constraints:\n"
        "              nullable: false\n"
    )


def test_drop_table_rolls_back_to_accepted_structure() -> None:
    document = yaml.safe_load(
        render_changelog(_changelog(model(CUSTOMER + LINES), model(CUSTOMER)))
    )

    (entry,) = document["databaseChangeLog"]
    changeset = entry["changeSet"]
    assert changeset["changes"] == [{"dropTable": {"tableName": "invoice_line"}}]
    create, key = changeset["rollback"]
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


def test_additions_carry_no_explicit_rollback() -> None:
    document = yaml.safe_load(render_changelog(_changelog(model(), model(CUSTOMER))))

    assert "rollback" not in document["databaseChangeLog"][0]["changeSet"]


def test_drop_rendering_is_byte_stable() -> None:
    first = render_changelog(_changelog(model(CUSTOMER + LINES), model(PHONE)))
    second = render_changelog(_changelog(model(CUSTOMER + LINES), model(PHONE)))

    assert first == second


def test_summary_lists_drops_but_not_rollback_blocks(tmp_path: Path) -> None:
    path = tmp_path / "changelog.yaml"
    LiquibaseYamlChangelogWriter().write(
        str(path), _changelog(model(PHONE + LINES), model(CUSTOMER))
    )

    summary = LiquibaseYamlChangelogReader().read(str(path))

    assert summary.dropped_tables == ("invoice_line",)
    assert summary.dropped_columns == (("customer", "phone"),)
    assert (summary.tables, summary.columns) == ((), ())


ORDER = """
  - name: purchase
    columns:
      - {name: id, type: bigint}
      - {name: customer_id, type: uuid}
    primary_key: [id]
    foreign_keys:
      - {columns: [customer_id], references: {table: customer, columns: [id]}}
"""
UNIQUE_EMAIL = CUSTOMER + "    unique:\n      - [email]\n"
CUSTOMER_KEY = ForeignKey((ColumnName("customer_id"),), TableName("customer"), (ColumnName("id"),))
EMAIL = UniqueSet((ColumnName("email"),))


def _columns(*names: str) -> tuple[ColumnName, ...]:
    return tuple(ColumnName(name) for name in names)


def test_constraint_names_do_not_depend_on_order() -> None:
    table = TableName("invoice_line")
    first = ForeignKey(_columns("a", "b"), TableName("line"), _columns("x", "y"))
    second = ForeignKey(_columns("b", "a"), TableName("line"), _columns("y", "x"))

    assert foreign_key_name(table, first) == foreign_key_name(table, second)
    assert unique_name(table, UniqueSet(_columns("a", "b"))) == unique_name(
        table, UniqueSet(_columns("b", "a"))
    )
    assert unique_name(table, UniqueSet(_columns("a"))) != unique_name(
        table, UniqueSet(_columns("b"))
    )
    assert re.fullmatch(r"fk_invoice_line_[0-9a-f]{8}", foreign_key_name(table, first))


def test_constraint_name_of_long_table_fits_postgresql() -> None:
    table = TableName("t" * 60)

    for name in (unique_name(table, EMAIL), foreign_key_name(table, CUSTOMER_KEY)):
        assert len(name) <= 63
        assert re.fullmatch(r"(uq|fk)_t{51}_[0-9a-f]{8}", name)


def test_constraints_are_rendered_exactly() -> None:
    text = render_changelog(_changelog(model(CUSTOMER), model(UNIQUE_EMAIL + ORDER)))
    uq = unique_name(TableName("customer"), EMAIL)
    fk = foreign_key_name(TableName("purchase"), CUSTOMER_KEY)

    assert text.split("- changeSet:\n")[2:] == [
        "    id: 20261017-153000-02\n"
        "    author: forge\n"
        "    logicalFilePath: db/changelog/20261017-153000.yaml\n"
        "    changes:\n"
        "    - addUniqueConstraint:\n"
        "        tableName: customer\n"
        "        columnNames: email\n"
        f"        constraintName: {uq}\n",
        "    id: 20261017-153000-03\n"
        "    author: forge\n"
        "    logicalFilePath: db/changelog/20261017-153000.yaml\n"
        "    changes:\n"
        "    - addForeignKeyConstraint:\n"
        "        baseTableName: purchase\n"
        "        baseColumnNames: customer_id\n"
        "        referencedTableName: customer\n"
        "        referencedColumnNames: id\n"
        f"        constraintName: {fk}\n",
    ]


def test_constraint_drops_are_rendered_exactly_with_rollback() -> None:
    text = render_changelog(
        _changelog(model(UNIQUE_EMAIL + ORDER), model(CUSTOMER + ORDER.split("    foreign")[0]))
    )
    uq = unique_name(TableName("customer"), EMAIL)
    fk = foreign_key_name(TableName("purchase"), CUSTOMER_KEY)

    assert text.split("- changeSet:\n")[1:] == [
        "    id: 20261017-153000-01\n"
        "    author: forge\n"
        "    logicalFilePath: db/changelog/20261017-153000.yaml\n"
        "    changes:\n"
        "    - dropForeignKeyConstraint:\n"
        "        baseTableName: purchase\n"
        f"        constraintName: {fk}\n"
        "    rollback:\n"
        "    - addForeignKeyConstraint:\n"
        "        baseTableName: purchase\n"
        "        baseColumnNames: customer_id\n"
        "        referencedTableName: customer\n"
        "        referencedColumnNames: id\n"
        f"        constraintName: {fk}\n",
        "    id: 20261017-153000-02\n"
        "    author: forge\n"
        "    logicalFilePath: db/changelog/20261017-153000.yaml\n"
        "    changes:\n"
        "    - dropUniqueConstraint:\n"
        "        tableName: customer\n"
        f"        constraintName: {uq}\n"
        "    rollback:\n"
        "    - addUniqueConstraint:\n"
        "        tableName: customer\n"
        "        columnNames: email\n"
        f"        constraintName: {uq}\n",
    ]


def test_drop_table_rollback_restores_unique_sets() -> None:
    document = yaml.safe_load(render_changelog(_changelog(model(UNIQUE_EMAIL), model())))

    (entry,) = document["databaseChangeLog"]
    create, key, unique = entry["changeSet"]["rollback"]
    assert "createTable" in create and "addPrimaryKey" in key
    assert unique == {
        "addUniqueConstraint": {
            "tableName": "customer",
            "columnNames": "email",
            "constraintName": unique_name(TableName("customer"), EMAIL),
        }
    }


def test_constraint_rendering_is_byte_stable() -> None:
    first = render_changelog(_changelog(model(UNIQUE_EMAIL + ORDER), model()))
    second = render_changelog(_changelog(model(UNIQUE_EMAIL + ORDER), model()))

    assert first == second


def test_summary_lists_added_and_dropped_constraints(tmp_path: Path) -> None:
    path = tmp_path / "changelog.yaml"
    writer = LiquibaseYamlChangelogWriter()
    reader = LiquibaseYamlChangelogReader()
    uq = ConstraintRef("unique", "customer", unique_name(TableName("customer"), EMAIL))
    fk = ConstraintRef(
        "foreign_key", "purchase", foreign_key_name(TableName("purchase"), CUSTOMER_KEY)
    )

    writer.write(str(path), _changelog(model(CUSTOMER), model(UNIQUE_EMAIL + ORDER)))
    added = reader.read(str(path))
    writer.write(str(path), _changelog(model(UNIQUE_EMAIL + ORDER), model()))
    dropped = reader.read(str(path))

    assert (added.constraints, added.dropped_constraints) == ((uq, fk), ())
    # Наборы удаляемой таблицы снимает dropTable: в сводку попадает только FK
    assert (dropped.constraints, dropped.dropped_constraints) == ((), (fk,))
