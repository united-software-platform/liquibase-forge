"""Команды CLI `forge`: каждый модуль регистрирует одну команду и исполняет её.

Модуль команды объявляет `register(subparsers)`, которая добавляет подкоманду и задаёт ей
`handler` через `set_defaults`. Новая команда — новый модуль в `COMMANDS`, без правки
ветвлений в `main`.
"""

from __future__ import annotations

from forge.cli.commands import (
    apply,
    close,
    generate,
    reconcile,
    report,
    resume,
    rollback,
    status,
    stop,
    validate,
)

COMMANDS = (validate, generate, apply, reconcile, rollback, status, stop, resume, close, report)
