"""Запись changelog данных YAML Liquibase: эталон, литералы, откат и повторяемость."""

from __future__ import annotations

from pathlib import Path

import yaml

from forge.migration.domain.stamp import OperationStamp
from forge.modeling.domain.draft import ColumnDraft
from forge.modeling.domain.identifier import ColumnName
from forge.seeding.domain.data_changelog import DataChangelog
from forge.seeding.domain.factory import SeedFactory
from forge.seeding.domain.seed_diff import SeedDiff
from forge.seeding.domain.seed_value import SeedValue
from forge.seeding.infrastructure.liquibase_data_changelog import (
    LiquibaseYamlDataChangelogWriter,
    literal,
    render_data_changelog,
)
from tests.seeding.support import (
    EXAMPLE_STAMP,
    MIGRATION_EXAMPLE,
    NULL,
    b,
    i,
    migration_example,
    model,
    row,
    s,
    seed,
    table,
)

STAMP = OperationStamp(EXAMPLE_STAMP)


def _example() -> DataChangelog:
    accepted, attempt = migration_example()
    return DataChangelog(STAMP, SeedDiff().between(accepted, attempt))


def test_example_matches_reference_file_byte_for_byte() -> None:
    expected = (MIGRATION_EXAMPLE / "changelog.yaml").read_text(encoding="utf-8")

    assert render_data_changelog(_example()) == expected


def test_repeated_write_gives_same_file(tmp_path: Path) -> None:
    writer = LiquibaseYamlDataChangelogWriter()
    first, second = tmp_path / "a" / "changelog.yaml", tmp_path / "b" / "changelog.yaml"

    writer.write(str(first), _example())
    writer.write(str(second), _example())

    assert first.read_bytes() == second.read_bytes()


def test_changesets_have_operation_identity_and_explicit_rollback() -> None:
    document = yaml.safe_load(render_data_changelog(_example()))

    changesets = [entry["changeSet"] for entry in document["databaseChangeLog"]]
    assert [c["id"] for c in changesets] == [f"{EXAMPLE_STAMP}-0{n}" for n in range(1, 5)]
    assert {c["author"] for c in changesets} == {"forge"}
    assert {c["logicalFilePath"] for c in changesets} == {f"db/changelog/{EXAMPLE_STAMP}.yaml"}
    assert all(c["rollback"] for c in changesets)


def test_rollback_of_several_rows_goes_in_reverse_order() -> None:
    document = yaml.safe_load(render_data_changelog(_example()))

    inserts = document["databaseChangeLog"][1]["changeSet"]
    assert [c["insert"]["columns"][0]["column"]["valueComputed"] for c in inserts["changes"]] == [
        "'paid'::VARCHAR(32)",
        "'new'::VARCHAR(32)",
    ]
    assert [c["delete"]["where"] for c in inserts["rollback"]] == [
        "code = 'new'::VARCHAR(32)",
        "code = 'paid'::VARCHAR(32)",
    ]


def test_deleted_row_is_restored_with_accepted_values() -> None:
    document = yaml.safe_load(render_data_changelog(_example()))

    deletion = document["databaseChangeLog"][3]["changeSet"]
    assert deletion["changes"] == [
        {"delete": {"tableName": "order_status", "where": "code = 'archived'::VARCHAR(32)"}}
    ]
    (restore,) = deletion["rollback"]
    assert {
        c["column"]["name"]: c["column"]["valueComputed"] for c in restore["insert"]["columns"]
    } == {
        "code": "'archived'::VARCHAR(32)",
        "group_code": "'active'::VARCHAR(16)",
        "title": "'Архив'::TEXT",
        "fee": "'0'::NUMERIC(12, 2)",
    }


def test_null_is_explicit_sql_null_not_yaml_null() -> None:
    document = yaml.safe_load(render_data_changelog(_example()))

    columns = document["databaseChangeLog"][1]["changeSet"]["changes"][1]["insert"]["columns"]
    assert columns[-1] == {"column": {"name": "fee", "valueComputed": "NULL"}}


LITERALS = model(
    table(
        "sample",
        ColumnDraft("code", "string", length=32),
        ColumnDraft("level", "integer"),
        ColumnDraft("title", "text"),
        ColumnDraft("enabled", "boolean"),
        ColumnDraft("moment", "timestamp_tz"),
        key=("code", "level"),
    )
)


def test_literals_cast_to_column_type_and_double_quotes() -> None:
    sample = LITERALS.tables[0]

    assert literal(sample, ColumnName("title"), SeedValue("O'Reilly")) == "'O''Reilly'::TEXT"
    assert literal(sample, ColumnName("level"), SeedValue(10)) == "'10'::INTEGER"
    assert literal(sample, ColumnName("enabled"), SeedValue(True)) == "'true'::BOOLEAN"
    assert (
        literal(sample, ColumnName("moment"), SeedValue("2026-01-01T00:00:00Z"))
        == "'2026-01-01T00:00:00Z'::TIMESTAMP WITH TIME ZONE"
    )
    assert literal(sample, ColumnName("title"), SeedValue.null()) == "NULL"


def test_where_covers_every_primary_key_column() -> None:
    old = seed(("sample", (row(code=s("a"), level=i(1), title=s("x"), enabled=b(True)),)))
    new = seed(("sample", (row(code=s("a"), level=i(1), title=s("y"), enabled=NULL),)))
    groups = SeedDiff().between(
        SeedFactory().create(LITERALS, old), SeedFactory().create(LITERALS, new)
    )

    document = yaml.safe_load(render_data_changelog(DataChangelog(STAMP, groups)))

    (change,) = document["databaseChangeLog"][0]["changeSet"]["changes"]
    assert change["update"]["where"] == "code = 'a'::VARCHAR(32) AND level = '1'::INTEGER"
    assert [c["column"]["name"] for c in change["update"]["columns"]] == ["title", "enabled"]


def test_quote_in_value_is_one_sql_literal() -> None:
    attempt = seed(("sample", (row(code=s("q"), level=i(1), title=s("O'Reilly")),)))
    groups = SeedDiff().between(
        SeedFactory().create(LITERALS, seed()), SeedFactory().create(LITERALS, attempt)
    )

    text = render_data_changelog(DataChangelog(STAMP, groups))

    assert "valueComputed: \"'O''Reilly'::TEXT\"" in text


def test_equal_seeds_give_empty_changelog() -> None:
    accepted, _ = migration_example()

    text = render_data_changelog(DataChangelog(STAMP, SeedDiff().between(accepted, accepted)))

    assert yaml.safe_load(text) == {"databaseChangeLog": []}


def test_remove_deletes_file_and_ignores_missing(tmp_path: Path) -> None:
    writer = LiquibaseYamlDataChangelogWriter()
    path = tmp_path / "changelog.yaml"
    path.write_text("устаревший", encoding="utf-8")

    writer.remove(str(path))
    writer.remove(str(path))

    assert not path.exists()
