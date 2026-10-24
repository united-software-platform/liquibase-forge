"""Сводка changelog данных `forge generate-seed`: строки из действий и их отката."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.migration.application.changelog_storage import ChangelogUnreadableError, RowRef
from forge.migration.domain.changelog import Changelog
from forge.migration.domain.model_diff import ModelDiff
from forge.migration.domain.stamp import OperationStamp
from forge.migration.infrastructure.liquibase_changelog import (
    LiquibaseYamlChangelogReader,
    LiquibaseYamlChangelogWriter,
)
from tests.migration.models import CUSTOMER, model
from tests.seeding.support import EXAMPLE_STAMP, MIGRATION_EXAMPLE

EXAMPLE = str(MIGRATION_EXAMPLE / "changelog.yaml")


def test_rows_of_data_changelog() -> None:
    summary = LiquibaseYamlChangelogReader().read(EXAMPLE)

    assert summary.logical_file_path == f"db/changelog/{EXAMPLE_STAMP}.yaml"
    assert summary.changeset_ids == tuple(f"{EXAMPLE_STAMP}-0{n}" for n in range(1, 5))
    assert summary.inserted_rows == (
        RowRef("status_group", "code = 'closed'::VARCHAR(16)"),
        RowRef("order_status", "code = 'paid'::VARCHAR(32)"),
        RowRef("order_status", "code = 'new'::VARCHAR(32)"),
    )
    assert summary.updated_rows == (
        RowRef("order_status", "code = 'draft'::VARCHAR(32)", (("title", "'Черновик'::TEXT"),)),
    )
    assert summary.deleted_rows == (
        RowRef(
            "order_status",
            "code = 'archived'::VARCHAR(32)",
            (
                ("code", "'archived'::VARCHAR(32)"),
                ("group_code", "'active'::VARCHAR(16)"),
                ("title", "'Архив'::TEXT"),
                ("fee", "'0'::NUMERIC(12, 2)"),
            ),
        ),
    )


def test_data_changelog_has_no_schema_objects() -> None:
    summary = LiquibaseYamlChangelogReader().read(EXAMPLE)

    assert (summary.tables, summary.columns, summary.dropped_tables) == ((), (), ())
    assert (summary.constraints, summary.dropped_constraints) == ((), ())


def test_model_changelog_has_no_rows(tmp_path: Path) -> None:
    path = tmp_path / "changelog.yaml"
    changes = ModelDiff().between(model(), model(CUSTOMER))
    LiquibaseYamlChangelogWriter().write(
        str(path), Changelog(OperationStamp("20261017-153000"), changes)
    )

    summary = LiquibaseYamlChangelogReader().read(str(path))

    assert summary.tables == ("customer",)
    assert (summary.inserted_rows, summary.updated_rows, summary.deleted_rows) == ((), (), ())


@pytest.mark.parametrize(
    "rollback",
    [
        "    rollback: []\n",
        "",
    ],
)
def test_data_changeset_without_row_rollback_is_unreadable(tmp_path: Path, rollback: str) -> None:
    path = tmp_path / "changelog.yaml"
    path.write_text(
        "databaseChangeLog:\n"
        "- changeSet:\n"
        "    id: 20261025-101500-01\n"
        "    author: forge\n"
        "    logicalFilePath: db/changelog/20261025-101500.yaml\n"
        "    changes:\n"
        "    - delete: {tableName: status, where: \"code = 'a'::VARCHAR(8)\"}\n" + rollback,
        encoding="utf-8",
    )

    with pytest.raises(ChangelogUnreadableError):
        LiquibaseYamlChangelogReader().read(str(path))
