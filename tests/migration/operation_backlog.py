"""Беклог операции в формате `templates/forge-model.md` для тестов Миграции."""

from __future__ import annotations

from pathlib import Path


def write_operation(
    directory: Path,
    subject: str = "20261017-153000",
    verdicts: tuple[str, str, str] = ("null", "null", "null"),
) -> Path:
    """Записать беклог операции `<directory>/tasks.md` и вернуть его путь."""
    path = directory / "tasks.md"
    path.write_text(
        "<!-- template_version: 1.0.0 -->\n"
        "---\n"
        'template_version: "1.0.0"\n'
        'generated: "2026-10-17"\n'
        "operation: forge-model\n"
        f'subject: "{subject}"\n'
        'runner: ".claude/commands/backlog/backlog-run.md"\n'
        "intent: >-\n  Таблица клиентов\n"
        "mode: auto\n"
        "gate:\n  close: null\n"
        "status: running\n"
        "verdict:\n"
        f"  attempt_1: {verdicts[0]}\n  attempt_2: {verdicts[1]}\n  attempt_3: {verdicts[2]}\n"
        "backlog:\n  attempt_1: null\n  attempt_2: null\n  attempt_3: null\n"
        "---\n\n# Операция построения модели\n\n---\n\nТекст после разделителя.\n",
        encoding="utf-8",
    )
    return path
