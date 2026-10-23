"""Changelog: `id` changeset по порядку изменений, неизменяемость."""

from __future__ import annotations

import dataclasses

import pytest

from forge.migration.domain.changelog import Changelog
from forge.migration.domain.changes import (
    AddColumn,
    CreateTable,
    UnsupportedChange,
    UnsupportedChangeError,
)
from forge.migration.domain.stamp import OperationStamp
from forge.modeling.domain.identifier import TableName
from tests.migration.models import CUSTOMER, model


def test_changesets_get_ids_in_order() -> None:
    customer = model(CUSTOMER).table(TableName("customer"))
    changes = (CreateTable(customer), AddColumn(customer.name, customer.columns[1], False))

    changelog = Changelog(OperationStamp("20261017-153000"), changes)

    assert [(c.id, c.change) for c in changelog.changesets] == [
        ("20261017-153000-01", changes[0]),
        ("20261017-153000-02", changes[1]),
    ]
    assert changelog.logical_file_path == "db/changelog/20261017-153000.yaml"


def test_empty_changelog() -> None:
    assert Changelog(OperationStamp("20261017-153000"), ()).changesets == ()


def test_changelog_is_immutable() -> None:
    changelog = Changelog(OperationStamp("20261017-153000"), ())

    with pytest.raises(dataclasses.FrozenInstanceError):
        changelog.changes = ()  # type: ignore[misc]


def test_non_additive_error_requires_changes() -> None:
    with pytest.raises(ValueError):
        UnsupportedChangeError([])
    error = UnsupportedChangeError([UnsupportedChange("table_removed", "t", None, "удалена")])
    assert error.changes[0].code == "table_removed"
