"""Перечень поставки `delivery.txt`: источники существуют, цели не пересекаются, лишнего нет."""

from __future__ import annotations

from pathlib import PurePosixPath

from tests.delivery.support import ROOT, delivery_entries

NOT_DELIVERED = ("tests", "openspec", "docs", "README.md")


def _overlaps(first: PurePosixPath, second: PurePosixPath) -> bool:
    return first == second or first in second.parents or second in first.parents


def test_every_source_exists() -> None:
    missing = [source for source, _ in delivery_entries() if not (ROOT / source).exists()]

    assert missing == []


def test_targets_do_not_overlap() -> None:
    targets = [PurePosixPath(target) for _, target in delivery_entries()]

    overlapping = [
        (first, second)
        for index, first in enumerate(targets)
        for second in targets[index + 1 :]
        if _overlaps(first, second)
    ]

    assert overlapping == []


def test_cli_code_goes_to_forge_subproject() -> None:
    entries = dict(delivery_entries())

    assert entries["src/forge"] == "tools/forge/src/forge"
    assert entries["pyproject.toml"] == "tools/forge/pyproject.toml"
    assert entries["uv.lock"] == "tools/forge/uv.lock"


def test_tests_and_documents_are_not_delivered() -> None:
    paths = [PurePosixPath(path) for entry in delivery_entries() for path in entry]

    delivered = [
        path
        for path in paths
        for excluded in map(PurePosixPath, NOT_DELIVERED)
        if _overlaps(path, excluded)
    ]

    assert delivered == []
