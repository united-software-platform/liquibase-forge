"""Разбор YAML модели: вид значений, состав полей, повторные ключи, синтаксис, чтение файла."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.modeling.application.model_reading import ModelUnreadableError
from forge.modeling.domain.draft import ColumnDraft, ForeignKeyDraft, TableDraft
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader, parse_model
from tests.modeling.example import EXAMPLE

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "model"

TABLE = """
  - name: customer
    columns:
      - name: id
        type: bigint
    primary_key: [id]
"""


def _model(tables: str) -> str:
    return "version: 1\ntables:\n" + tables


def _violations(text: str) -> list[tuple[str, str]]:
    return [(v.path, v.code) for v in parse_model(text).violations]


def _column(body: str) -> str:
    """Таблица `tables[0]` с колонкой `columns[0]`, заданной телом `body`."""
    lines = "\n".join("        " + line for line in body.strip().splitlines())
    return _model(
        "  - name: customer\n    columns:\n      - name: id\n        type: bigint\n"
        f"      -\n{lines}\n    primary_key: [id]\n"
    )


def test_example_fixture_gives_example_draft() -> None:
    reading = YamlModelDraftReader().read(str(FIXTURES / "example.yaml"))

    assert reading.violations == ()
    assert reading.draft == EXAMPLE


def test_empty_tables() -> None:
    reading = parse_model("version: 1\ntables: []\n")

    assert reading.violations == ()
    assert reading.draft.tables == ()


def test_optional_column_fields_are_absent_as_none() -> None:
    reading = parse_model(_column("name: note\ntype: text"))

    assert reading.draft.tables[0].columns[1] == ColumnDraft("note", "text")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("tables: []\n", [("version", "missing_field")]),
        ("version: 2\ntables: []\n", [("version", "unsupported_version")]),
        ("version: '1'\ntables: []\n", [("version", "unsupported_version")]),
        ("version: 1.0\ntables: []\n", [("version", "unsupported_version")]),
        ("version: true\ntables: []\n", [("version", "unsupported_version")]),
    ],
)
def test_version(text: str, expected: list[tuple[str, str]]) -> None:
    assert _violations(text) == expected


def test_unsupported_version_skips_tables() -> None:
    reading = parse_model("version: 2\ntables:\n" + TABLE + "  - 42\n")

    assert [(v.path, v.code) for v in reading.violations] == [("version", "unsupported_version")]
    assert reading.draft.tables == ()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", [("", "wrong_kind")]),
        ("# только комментарий\n", [("", "wrong_kind")]),
        ("- 1\n", [("", "wrong_kind")]),
        ("version: 1\n", [("tables", "missing_field")]),
        ("version: 1\ntables: customer\n", [("tables", "wrong_kind")]),
        ("version: 1\ntables:\n", [("tables", "wrong_kind")]),
    ],
)
def test_root_structure(text: str, expected: list[tuple[str, str]]) -> None:
    assert _violations(text) == expected


def test_unknown_root_field_does_not_stop_tables() -> None:
    reading = parse_model("version: 1\nschema: public\ntables:\n" + TABLE)

    assert [(v.path, v.code) for v in reading.violations] == [("schema", "unknown_field")]
    assert [table.name for table in reading.draft.tables] == ["customer"]


def test_unknown_column_field() -> None:
    assert _violations(_column("name: note\ntype: text\ndefault: x")) == [
        ("tables[0].columns[1].default", "unknown_field")
    ]


def test_duplicate_key_is_reported_and_first_value_is_not_silently_replaced() -> None:
    reading = parse_model(_column("name: note\ntype: text\ntype: uuid"))

    assert [(v.path, v.code) for v in reading.violations] == [
        ("tables[0].columns[1].type", "duplicate_key")
    ]
    assert reading.draft.tables == ()


def test_merge_key_is_unknown_field() -> None:
    text = _model(
        "  - name: customer\n"
        "    columns:\n"
        "      - &base {name: id, type: bigint}\n"
        "      - <<: *base\n"
        "        name: code\n"
        "    primary_key: [id]\n"
    )

    assert _violations(text) == [
        ("tables[0].columns[1].<<", "unknown_field"),
        ("tables[0].columns[1].type", "missing_field"),
    ]


def test_aliases_are_resolved() -> None:
    text = _model(
        "  - name: customer\n"
        "    columns:\n"
        "      - {name: id, type: &t bigint}\n"
        "      - {name: parent_id, type: *t}\n"
        "    primary_key: [id]\n"
    )

    assert parse_model(text).draft.tables[0].columns[1] == ColumnDraft("parent_id", "bigint")


@pytest.mark.parametrize(
    ("body", "path"),
    [
        ("name: note\ntype: string\nlength: true", "length"),
        ("name: note\ntype: string\nlength: '10'", "length"),
        ("name: note\ntype: string\nlength: 10.5", "length"),
        ("name: note\ntype: string\nlength:", "length"),
        ("name: note\ntype: text\nnullable: 'no'", "nullable"),
        ("name: note\ntype: text\nnullable: 0", "nullable"),
        ("name: 42\ntype: text", "name"),
        ("name: note\ntype: [text]", "type"),
    ],
)
def test_wrong_kind_of_value(body: str, path: str) -> None:
    assert _violations(_column(body)) == [(f"tables[0].columns[1].{path}", "wrong_kind")]


def test_yaml_boolean_name_needs_quotes() -> None:
    reading = parse_model(_column("name: no\ntype: text"))

    (violation,) = reading.violations
    assert (violation.path, violation.code) == ("tables[0].columns[1].name", "wrong_kind")
    assert "кавычки" in violation.message
    assert parse_model(_column("name: 'no'\ntype: text")).violations == ()


def test_yaml_booleans_are_accepted_for_nullable() -> None:
    reading = parse_model(_column("name: note\ntype: text\nnullable: no"))

    assert reading.draft.tables[0].columns[1].nullable is False


def test_integer_forms_are_accepted() -> None:
    reading = parse_model(_column("name: note\ntype: string\nlength: 1_000"))

    assert reading.draft.tables[0].columns[1].length == 1000


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        ("  - customer\n", [("tables[0]", "wrong_kind")]),
        (
            "  - name: customer\n",
            [("tables[0].columns", "missing_field"), ("tables[0].primary_key", "missing_field")],
        ),
        (
            "  - name: customer\n    columns: id\n    primary_key: [id]\n",
            [("tables[0].columns", "wrong_kind")],
        ),
        (
            "  - name: customer\n    columns:\n      - id\n    primary_key: [id]\n",
            [("tables[0].columns[0]", "wrong_kind")],
        ),
        (
            "  - name: customer\n    columns: []\n    primary_key: id\n",
            [("tables[0].primary_key", "wrong_kind")],
        ),
        (
            "  - name: customer\n    columns: []\n    primary_key: [id, 7]\n",
            [("tables[0].primary_key[1]", "wrong_kind")],
        ),
    ],
)
def test_table_structure(table: str, expected: list[tuple[str, str]]) -> None:
    assert _violations(_model(table)) == expected


def test_table_with_structural_violation_is_excluded_from_draft() -> None:
    text = _model(
        TABLE
        + "  - name: invoice\n    columns:\n      - {name: id, type: bigint, default: 0}\n"
        + "    primary_key: [id]\n"
        + TABLE.replace("customer", "payment")
    )

    reading = parse_model(text)

    assert [(v.path, v.code) for v in reading.violations] == [
        ("tables[1].columns[0].default", "unknown_field")
    ]
    assert [(table.position, table.name) for table in reading.draft.tables] == [
        (0, "customer"),
        (2, "payment"),
    ]


def test_empty_lists_are_kept_for_domain_checks() -> None:
    reading = parse_model(_model("  - name: customer\n    columns: []\n    primary_key: []\n"))

    assert reading.violations == ()
    assert reading.draft.tables == (TableDraft(0, "customer", (), ()),)


def _relations(body: str) -> str:
    """Таблица `tables[0]` с колонками `id`, `parent_id` и полями связей из тела `body`."""
    lines = "\n".join("    " + line for line in body.strip().splitlines())
    return _model(
        "  - name: category\n    columns:\n      - {name: id, type: bigint}\n"
        f"      - {{name: parent_id, type: bigint}}\n    primary_key: [id]\n{lines}\n"
    )


def test_relations_are_read_into_draft() -> None:
    reading = parse_model(
        _relations(
            "unique:\n  - [parent_id, id]\nforeign_keys:\n"
            "  - columns: [parent_id]\n    references: {table: category, columns: [id]}"
        )
    )

    assert reading.violations == ()
    (table,) = reading.draft.tables
    assert table.unique == (("parent_id", "id"),)
    assert table.foreign_keys == (ForeignKeyDraft(("parent_id",), "category", ("id",)),)


def test_absent_relations_are_empty() -> None:
    (table,) = parse_model(_model(TABLE)).draft.tables

    assert (table.unique, table.foreign_keys) == ((), ())


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("unique: parent_id", [("tables[0].unique", "wrong_kind")]),
        ("unique: [parent_id]", [("tables[0].unique[0]", "wrong_kind")]),
        ("unique: [[parent_id, 7]]", [("tables[0].unique[0][1]", "wrong_kind")]),
        ("foreign_keys: {columns: [parent_id]}", [("tables[0].foreign_keys", "wrong_kind")]),
        ("foreign_keys: [parent_id]", [("tables[0].foreign_keys[0]", "wrong_kind")]),
        (
            "foreign_keys:\n  - columns: [parent_id]",
            [("tables[0].foreign_keys[0].references", "missing_field")],
        ),
        (
            "foreign_keys:\n  - references: {table: category, columns: [id]}",
            [("tables[0].foreign_keys[0].columns", "missing_field")],
        ),
        (
            "foreign_keys:\n  - columns: parent_id\n"
            "    references: {table: category, columns: [id]}",
            [("tables[0].foreign_keys[0].columns", "wrong_kind")],
        ),
        (
            "foreign_keys:\n  - columns: [parent_id]\n    references: category",
            [("tables[0].foreign_keys[0].references", "wrong_kind")],
        ),
        (
            "foreign_keys:\n  - columns: [parent_id]\n    references: {columns: [id]}",
            [("tables[0].foreign_keys[0].references.table", "missing_field")],
        ),
        (
            "foreign_keys:\n  - columns: [parent_id]\n    references: {table: category}",
            [("tables[0].foreign_keys[0].references.columns", "missing_field")],
        ),
        (
            "foreign_keys:\n  - columns: [parent_id]\n    references: {table: 7, columns: [id]}",
            [("tables[0].foreign_keys[0].references.table", "wrong_kind")],
        ),
        (
            "foreign_keys:\n  - columns: [parent_id]\n"
            "    references: {table: category, columns: [id], schema: public}",
            [("tables[0].foreign_keys[0].references.schema", "unknown_field")],
        ),
        (
            "foreign_keys:\n  - columns: [parent_id]\n"
            "    references: {table: category, columns: [id]}\n    on_delete: cascade",
            [("tables[0].foreign_keys[0].on_delete", "unknown_field")],
        ),
    ],
)
def test_relations_structure(body: str, expected: list[tuple[str, str]]) -> None:
    reading = parse_model(_relations(body))

    assert [(v.path, v.code) for v in reading.violations] == expected
    assert reading.draft.tables == ()


def test_excluded_table_names_are_kept() -> None:
    reading = parse_model(
        _model(TABLE + "  - name: invoice\n    columns: []\n    primary_key: [id]\n    unique: x\n")
    )

    assert reading.draft.excluded == ("invoice",)
    assert [table.name for table in reading.draft.tables] == ["customer"]


def test_yaml_syntax_error_has_line_and_column() -> None:
    reading = parse_model("version: 1\ntables: [\n  {name: x,\n")

    (violation,) = reading.violations
    assert (violation.path, violation.code) == ("", "yaml_syntax")
    assert "строка" in violation.message and "столбец" in violation.message
    assert reading.draft.tables == ()


def test_several_documents_are_syntax_error() -> None:
    assert _violations("version: 1\ntables: []\n---\nversion: 1\n") == [("", "yaml_syntax")]


def test_unknown_tag_is_wrong_kind() -> None:
    assert _violations(_column("name: note\ntype: !custom text")) == [
        ("tables[0].columns[1].type", "wrong_kind")
    ]


def test_missing_file_is_unreadable(tmp_path: Path) -> None:
    with pytest.raises(ModelUnreadableError) as caught:
        YamlModelDraftReader().read(str(tmp_path / "missing.yaml"))

    assert caught.value.path == str(tmp_path / "missing.yaml")


def test_directory_is_unreadable(tmp_path: Path) -> None:
    with pytest.raises(ModelUnreadableError):
        YamlModelDraftReader().read(str(tmp_path))


def test_non_utf8_file_is_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "model.yaml"
    path.write_bytes("version: 1\ntables: []\n# модель\n".encode("cp1251"))

    with pytest.raises(ModelUnreadableError):
        YamlModelDraftReader().read(str(path))
