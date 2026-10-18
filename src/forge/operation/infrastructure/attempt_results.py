"""Чтение `reconcile.json` и `rollback.json` каталога попытки."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from forge.operation.application.accepted_state import (
    DiscrepancySummary,
    ReconcileSummary,
    RollbackSummary,
)

RECONCILE = "reconcile.json"
ROLLBACK = "rollback.json"


def _load(path: Path) -> dict[str, Any] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


class JsonAttemptResultsReader:
    """Реализация чтения результатов попытки; нечитаемый файл считается отсутствующим."""

    def reconcile(self, attempt_directory: str) -> ReconcileSummary | None:
        document = _load(Path(attempt_directory) / RECONCILE)
        if document is None:
            return None
        return ReconcileSummary(
            verdict=str(document.get("verdict")),
            discrepancies=tuple(
                DiscrepancySummary(
                    kind=str(item.get("kind")),
                    table=item.get("table"),
                    column=item.get("column"),
                    changeset=item.get("changeset"),
                    expected=str(item.get("expected")),
                    actual=str(item.get("actual")),
                    message=str(item.get("message")),
                )
                for item in document.get("discrepancies") or []
                if isinstance(item, dict)
            ),
        )

    def rollback(self, attempt_directory: str) -> RollbackSummary | None:
        document = _load(Path(attempt_directory) / ROLLBACK)
        if document is None:
            return None
        return RollbackSummary(
            action=str(document.get("action")),
            rolled_back=int(document.get("rolled_back") or 0),
            verified=document.get("verified") is True,
            fallback_reason=document.get("fallback_reason"),
        )
