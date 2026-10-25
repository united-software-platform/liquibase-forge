"""Разбор YAML seed: корень, таблицы, строки, сырые значения, синтаксис и чтение файла."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.seeding.application.seed_reading import SeedUnreadableError
from forge.seeding.domain.draft import RawValue, RowDraft, ScalarKind, SeedTableDraft
from forge.seeding.infrastructure.yaml_reader import YamlSeedDraftReader, parse_seed


def _violations(text: str) -> list[tuple[str, str]]:
    return [(v.path, v.code) for v in parse_seed(text).violations]


def _seed(tables: str) -> str:
    return "version: 1\ntables:\n" + tables


def _values(row: str) -> tuple[tuple[str, RawValue], ...]:
    reading = parse_seed(_seed(f"  - name: kind\n    rows:\n      - {row}\n"))
    assert reading.violations == ()
    return reading.draft.tables[0].rows[0].values


def test_empty_seed() -> None:
    reading = parse_seed("version: 1\ntables: []\n")

    assert (reading.violations, reading.draft.tables) == ((), ())


def test_tables_and_rows_in_document_order() -> None:
    text = _seed(
        "  - name: order_status\n    rows:\n      - {code: new, sort_order: 10}\n"
        "  - name: kind\n    rows: []\n"
    )

    reading = parse_seed(text)

    assert reading.violations == ()
    assert reading.draft.tables == (
        SeedTableDraft(
            0,
            "order_status",
            (
                RowDraft(
                    (
                        ("code", RawValue(ScalarKind.STRING, "new")),
                        ("sort_order", RawValue(ScalarKind.INTEGER, "10")),
                    )
                ),
            ),
        ),
        SeedTableDraft(1, "kind", ()),
    )


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ('{v: "10"}', RawValue(ScalarKind.STRING, "10")),
        ("{v: 0x0A}", RawValue(ScalarKind.INTEGER, "10")),
        ("{v: -3}", RawValue(ScalarKind.INTEGER, "-3")),
        ("{v: yes}", RawValue(ScalarKind.BOOLEAN, "true")),
        ("{v: false}", RawValue(ScalarKind.BOOLEAN, "false")),
        ("{v: 12.50}", RawValue(ScalarKind.FLOAT, "12.50")),
        ("{v: null}", RawValue(ScalarKind.NULL, "null")),
        ("{v: }", RawValue(ScalarKind.NULL, "")),
        ("{v: 2026-02-28}", RawValue(ScalarKind.TIMESTAMP, "2026-02-28")),
        ('{v: "2026-02-28"}', RawValue(ScalarKind.STRING, "2026-02-28")),
        ("{v: [1, 2]}", RawValue(ScalarKind.OTHER, "список")),
        ("{v: {a: 1}}", RawValue(ScalarKind.OTHER, "отображение")),
    ],
)
def test_raw_values(row: str, expected: RawValue) -> None:
    assert _values(row) == (("v", expected),)


def test_unquoted_date_is_read_as_text() -> None:
    assert _values("{starts_on: 2026-02-28}") == (
        ("starts_on", RawValue(ScalarKind.TIMESTAMP, "2026-02-28")),
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("version: 2\ntables: []\n", [("version", "unsupported_version")]),
        ('version: "1"\ntables: []\n', [("version", "unsupported_version")]),
        ("tables: []\n", [("version", "missing_field")]),
        ("version: 1\n", [("tables", "missing_field")]),
        ("version: 1\ntables: []\ndata: []\n", [("data", "unknown_field")]),
        ("version: 1\nversion: 1\ntables: []\n", [("version", "duplicate_key")]),
        ("version: 1\ntables: {}\n", [("tables", "wrong_kind")]),
        ("[]\n", [("", "wrong_kind")]),
        ("", [("", "wrong_kind")]),
        ("version: 1\ntables: [\n", [("", "yaml_syntax")]),
        (_seed("  - name: kind\n"), [("tables[0].rows", "missing_field")]),
        (_seed("  - rows: []\n"), [("tables[0].name", "missing_field")]),
        (_seed("  - {name: kind, rows: [], where: x}\n"), [("tables[0].where", "unknown_field")]),
        (_seed("  - {name: 1, rows: []}\n"), [("tables[0].name", "wrong_kind")]),
        (_seed("  - {name: kind, rows: {}}\n"), [("tables[0].rows", "wrong_kind")]),
        (_seed("  - {name: kind, rows: [[a]]}\n"), [("tables[0].rows[0]", "wrong_kind")]),
        (_seed("  - kind\n"), [("tables[0]", "wrong_kind")]),
        (
            _seed("  - name: kind\n    rows:\n      - code: a\n        code: b\n"),
            [("tables[0].rows[0].code", "duplicate_key")],
        ),
        (_seed("  - {name: kind, rows: [{1: a}]}\n"), [("tables[0].rows[0].1", "wrong_kind")]),
    ],
)
def test_structure_violation(text: str, expected: list[tuple[str, str]]) -> None:
    assert _violations(text) == expected


def test_version_violation_stops_tables() -> None:
    reading = parse_seed("version: 3\ntables:\n  - {name: kind, rows: [x]}\n")

    assert [(v.path, v.code) for v in reading.violations] == [("version", "unsupported_version")]
    assert reading.draft.tables == ()


def test_table_with_structure_violation_is_excluded() -> None:
    reading = parse_seed(
        _seed("  - {name: kind, rows: [x]}\n  - {name: other, rows: []}\n  - {rows: []}\n")
    )

    assert [t.name for t in reading.draft.tables] == ["other"]
    assert reading.draft.excluded == ("kind",)
    assert [(v.path, v.code) for v in reading.violations] == [
        ("tables[0].rows[0]", "wrong_kind"),
        ("tables[2].name", "missing_field"),
    ]


def test_syntax_error_names_line() -> None:
    message = parse_seed("version: 1\ntables: [\n").violations[0].message

    assert "строка" in message


def test_reads_file(tmp_path: Path) -> None:
    path = tmp_path / "seed.yaml"
    path.write_text("version: 1\ntables: []\n", encoding="utf-8")

    assert YamlSeedDraftReader().read(str(path)).violations == ()


@pytest.mark.parametrize("make", ["missing", "directory", "binary"])
def test_unreadable_file(make: str, tmp_path: Path) -> None:
    path = tmp_path / "seed.yaml"
    if make == "directory":
        path.mkdir()
    elif make == "binary":
        path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(SeedUnreadableError) as error:
        YamlSeedDraftReader().read(str(path))

    assert error.value.path == str(path)
