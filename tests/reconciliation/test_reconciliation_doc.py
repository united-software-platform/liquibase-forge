"""Пример `reconcile.json` из `docs/reconciliation.md` совпадает с выводом сценария сверки."""

from __future__ import annotations

import json
import re
from pathlib import Path

from forge.reconciliation.application.reconcile.output import DiscrepancyView, ReconcileOutput
from forge.reconciliation.application.reconcile.use_case import reconcile_document
from forge.reconciliation.domain.actual_schema import ActualTable
from forge.reconciliation.domain.schema_comparison import SchemaComparison
from tests.migration.models import CUSTOMER, model
from tests.reconciliation.schemas import column, schema

DOCUMENT = Path(__file__).resolve().parents[2] / "docs" / "reconciliation.md"


def _example() -> dict[str, object]:
    text = DOCUMENT.read_text(encoding="utf-8")
    section = text.split("\n## Файл reconcile.json\n", 1)[1]
    match = re.search(r"```json\n(.*?)```", section, re.S)
    assert match, "в разделе нет примера reconcile.json"
    example = json.loads(match.group(1))
    assert isinstance(example, dict)
    return example


def test_example_matches_command_output() -> None:
    example = _example()
    table = ActualTable(
        "customer",
        (
            column("id", "uuid", nullable=False),
            column("email", "string", nullable=False, length=320),
        ),
        ("id",),
    )
    found = SchemaComparison().compare(model(CUSTOMER), schema(table))
    output = ReconcileOutput(
        result_path="",
        model_path=str(example["model"]),
        changelog_path=str(example["changelog"]),
        database=str(example["database"]),
        verdict="failure",
        discrepancies=tuple(
            DiscrepancyView(d.kind, d.table, d.column, d.changeset, d.expected, d.actual, d.message)
            for d in found
        ),
    )

    assert reconcile_document(output) == example
