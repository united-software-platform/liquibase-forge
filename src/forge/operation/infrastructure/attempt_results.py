"""Чтение `reconcile.json` и `rollback.json` каталога попытки и удалений changelog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from forge.operation.application.accepted_state import (
    DestructiveChange,
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

    def destructive(self, changelog: str) -> tuple[DestructiveChange, ...]:
        return _destructive(changelog)


def _destructive(path: str) -> tuple[DestructiveChange, ...]:
    """Удаления changelog по блокам `changes`: только формы `dropTable` и `dropColumn`.

    Формат changelog знает запись контекста Миграция; здесь читаются только эти две формы,
    и тест сверяет их с выводом записи.
    """
    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        found: list[DestructiveChange] = []
        for entry in document["databaseChangeLog"] or []:
            for change in entry["changeSet"]["changes"]:
                if "dropTable" in change:
                    found.append(DestructiveChange(str(change["dropTable"]["tableName"]), None))
                elif "dropColumn" in change:
                    dropped = change["dropColumn"]
                    found.append(
                        DestructiveChange(str(dropped["tableName"]), str(dropped["columnName"]))
                    )
    except (OSError, UnicodeDecodeError, yaml.YAMLError, KeyError, TypeError):
        return ()
    return tuple(found)
