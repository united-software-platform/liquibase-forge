"""Чтение changeset из changelog `forge generate`."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.migration.domain.changelog import Changelog
from forge.migration.domain.model_diff import ModelDiff
from forge.migration.domain.stamp import OperationStamp
from forge.migration.infrastructure.liquibase_changelog import LiquibaseYamlChangelogWriter
from forge.reconciliation.application.contracts import ChangelogUnreadableError
from forge.reconciliation.domain.journal_check import ExpectedChangeSet
from forge.reconciliation.infrastructure.changeset_list_reader import YamlChangesetListReader
from tests.migration.models import CUSTOMER, INVOICE, model

FILE = "db/changelog/20261017-153000.yaml"


def _write(path: Path, attempt: str) -> None:
    changes = ModelDiff().between(model(), model(attempt)) if attempt else ()
    LiquibaseYamlChangelogWriter().write(
        str(path), Changelog(OperationStamp("20261017-153000"), changes)
    )


def test_changesets_of_generated_changelog(tmp_path: Path) -> None:
    path = tmp_path / "changelog.yaml"
    _write(path, CUSTOMER + INVOICE)

    assert YamlChangesetListReader().read(str(path)) == (
        ExpectedChangeSet("20261017-153000-01", "forge", FILE),
        ExpectedChangeSet("20261017-153000-02", "forge", FILE),
    )


def test_empty_changelog(tmp_path: Path) -> None:
    path = tmp_path / "changelog.yaml"
    _write(path, "")

    assert YamlChangesetListReader().read(str(path)) == ()


@pytest.mark.parametrize("text", ["databaseChangeLog: [{changeSet: {id: x}}]\n", "[: x\n", "- 1\n"])
def test_foreign_changelog(tmp_path: Path, text: str) -> None:
    path = tmp_path / "changelog.yaml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ChangelogUnreadableError):
        YamlChangesetListReader().read(str(path))


def test_missing_changelog(tmp_path: Path) -> None:
    with pytest.raises(ChangelogUnreadableError):
        YamlChangesetListReader().read(str(tmp_path / "changelog.yaml"))
