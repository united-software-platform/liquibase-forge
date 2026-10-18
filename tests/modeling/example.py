"""Черновик примера модели из `docs/model-format.md` и `tests/fixtures/model/example.yaml`."""

from __future__ import annotations

from forge.modeling.domain.draft import ColumnDraft, DataModelDraft, TableDraft

EXAMPLE = DataModelDraft(
    (
        TableDraft(
            0,
            "customer",
            (
                ColumnDraft("id", "uuid"),
                ColumnDraft("email", "string", nullable=False, length=255),
                ColumnDraft("full_name", "text"),
                ColumnDraft("created_at", "timestamp_tz", nullable=False),
            ),
            ("id",),
        ),
        TableDraft(
            1,
            "invoice_line",
            (
                ColumnDraft("invoice_id", "bigint"),
                ColumnDraft("line_no", "integer"),
                ColumnDraft("amount", "decimal", nullable=False, precision=12, scale=2),
                ColumnDraft("is_paid", "boolean"),
                ColumnDraft("due_date", "date"),
                ColumnDraft("created_at", "timestamp"),
            ),
            ("invoice_id", "line_no"),
        ),
    )
)
