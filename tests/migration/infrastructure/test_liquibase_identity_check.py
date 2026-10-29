"""Запись changelog генерации значения и перечня значений: определения, имена, откаты, сводка."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from forge.migration.application.changelog_storage import ChangelogUnreadableError, ConstraintRef
from forge.migration.domain.changelog import Changelog
from forge.migration.domain.model_diff import ModelDiff
from forge.migration.domain.stamp import OperationStamp
from forge.migration.infrastructure.liquibase_changelog import (
    LiquibaseYamlChangelogReader,
    LiquibaseYamlChangelogWriter,
    check_name,
    render_changelog,
)
from forge.modeling.domain.data_model import DataModel
from forge.modeling.domain.identifier import ColumnName, TableName
from forge.modeling.domain.value_list import ValueList
from tests.migration.models import model

STAMP = OperationStamp("20261017-153000")
IDENTITY = {
    "name": "id",
    "type": "BIGINT",
    "autoIncrement": True,
    "generationType": "BY DEFAULT",
    "constraints": {"nullable": False},
}
EVENT = """
  - name: event
    columns:
      - {name: id, type: bigint, generated: identity}
      - {name: source, type: string, length: 16, check: [manual, collector]}
    primary_key: [id]
"""
EVENT_PLAIN = """
  - name: event
    columns:
      - {name: id, type: bigint, generated: identity}
      - {name: source, type: string, length: 16}
    primary_key: [id]
"""


def _document(accepted: DataModel, attempt: DataModel) -> Any:
    changelog = Changelog(STAMP, ModelDiff().between(accepted, attempt))
    return yaml.safe_load(render_changelog(changelog))


def _changesets(accepted: DataModel, attempt: DataModel) -> list[dict[str, Any]]:
    return [entry["changeSet"] for entry in _document(accepted, attempt)["databaseChangeLog"]]


def _name() -> str:
    return check_name(TableName("event"), ColumnName("source"), ValueList(("collector", "manual")))


def test_identity_column_in_create_table() -> None:
    create, _check = _changesets(model(), model(EVENT))

    columns = [c["column"] for c in create["changes"][0]["createTable"]["columns"]]
    assert columns[0] == IDENTITY
    assert "autoIncrement" not in columns[1]


def test_identity_column_in_add_column_and_drop_column_rollback() -> None:
    without = """
  - name: task
    columns:
      - {name: code, type: text}
    primary_key: [code]
"""
    with_seq = without.replace(
        "    primary_key",
        "      - {name: seq_no, type: integer, generated: identity}\n    primary_key",
    )

    (added,) = _changesets(model(without), model(with_seq))
    (dropped,) = _changesets(model(with_seq), model(without))

    expected = {
        "name": "seq_no",
        "type": "INTEGER",
        "autoIncrement": True,
        "generationType": "BY DEFAULT",
        "constraints": {"nullable": False},
    }
    assert added["changes"][0]["addColumn"]["columns"] == [{"column": expected}]
    assert dropped["rollback"][0]["addColumn"]["columns"] == [{"column": expected}]


def test_drop_table_rollback_restores_identity_and_checks() -> None:
    (table,) = _changesets(model(EVENT), model())

    assert table["changes"] == [{"dropTable": {"tableName": "event"}}]
    create, _key, restored = table["rollback"]
    assert create["createTable"]["columns"][0]["column"] == IDENTITY
    assert restored == {
        "sql": {
            "sql": f"ALTER TABLE event ADD CONSTRAINT {_name()} "
            "CHECK (source IN ('collector', 'manual'))"
        }
    }


def test_check_is_rendered_exactly_as_separate_changeset() -> None:
    changelog = Changelog(STAMP, ModelDiff().between(model(EVENT_PLAIN), model(EVENT)))

    assert render_changelog(changelog) == (
        "# Changelog операции 20261017-153000: построен forge generate, вручную не правится\n"
        "databaseChangeLog:\n"
        "- changeSet:\n"
        "    id: 20261017-153000-01\n"
        "    author: forge\n"
        "    logicalFilePath: db/changelog/20261017-153000.yaml\n"
        "    changes:\n"
        "    - sql:\n"
        f"        sql: ALTER TABLE event ADD CONSTRAINT {_name()} "
        "CHECK (source IN ('collector', 'manual'))\n"
        "    rollback:\n"
        "    - sql:\n"
        f"        sql: ALTER TABLE event DROP CONSTRAINT {_name()}\n"
    )


def test_check_drop_rolls_back_to_accepted_values() -> None:
    (changeset,) = _changesets(model(EVENT), model(EVENT_PLAIN))

    assert changeset["changes"] == [
        {"sql": {"sql": f"ALTER TABLE event DROP CONSTRAINT {_name()}"}}
    ]
    assert changeset["rollback"] == [
        {
            "sql": {
                "sql": f"ALTER TABLE event ADD CONSTRAINT {_name()} "
                "CHECK (source IN ('collector', 'manual'))"
            }
        }
    ]


def test_check_literals_double_quotes_and_integers_are_numbers() -> None:
    quoted = (
        EVENT_PLAIN.replace("length: 16}", 'length: 16, check: ["o\'clock"]}')
        + """
  - name: task
    columns:
      - {name: id, type: bigint}
      - {name: priority, type: integer, check: [3, 1, 2]}
    primary_key: [id]
"""
    )
    changes = [c["changes"][0]["sql"]["sql"] for c in _changesets(model(), model(quoted))[2:]]

    assert changes[0].endswith("CHECK (source IN ('o''clock'))")
    assert changes[1].endswith("CHECK (priority IN (1, 2, 3))")


def test_check_name_does_not_depend_on_value_order() -> None:
    first = check_name(TableName("event"), ColumnName("source"), ValueList(("a", "b")))
    second = check_name(TableName("event"), ColumnName("source"), ValueList(("b", "a")))
    other = check_name(TableName("event"), ColumnName("source"), ValueList(("a", "b", "c")))

    assert first == second != other
    assert first.startswith("ck_event_") and len(first) == len("ck_event_") + 8


def test_check_name_of_long_table_fits_postgresql() -> None:
    name = check_name(TableName("t" * 60), ColumnName("source"), ValueList(("a",)))

    assert len(name) <= 63


def test_summary_lists_added_and_dropped_checks(tmp_path: Path) -> None:
    path = tmp_path / "changelog.yaml"
    writer = LiquibaseYamlChangelogWriter()
    reader = LiquibaseYamlChangelogReader()

    writer.write(str(path), Changelog(STAMP, ModelDiff().between(model(EVENT_PLAIN), model(EVENT))))
    added = reader.read(str(path))
    writer.write(str(path), Changelog(STAMP, ModelDiff().between(model(EVENT), model(EVENT_PLAIN))))
    dropped = reader.read(str(path))

    assert added.constraints == (ConstraintRef("check", "event", _name()),)
    assert dropped.dropped_constraints == (ConstraintRef("check", "event", _name()),)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE event",
        "ALTER TABLE event ADD CONSTRAINT uq_event_1 UNIQUE (source)",
    ],
)
def test_foreign_sql_is_unreadable(tmp_path: Path, sql: str) -> None:
    path = tmp_path / "changelog.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "databaseChangeLog": [
                    {
                        "changeSet": {
                            "id": "20261017-153000-01",
                            "author": "forge",
                            "logicalFilePath": "db/changelog/20261017-153000.yaml",
                            "changes": [{"sql": {"sql": sql}}],
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ChangelogUnreadableError):
        LiquibaseYamlChangelogReader().read(str(path))
