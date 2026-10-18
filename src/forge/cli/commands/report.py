"""Команда `forge report --operation <беклог>`: итоговый отчёт операции для LLM."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from typing import Any

from forge.cli.commands.close import ACCEPTED_ROOT
from forge.cli.commands.operation_support import operation_payload, read_repository
from forge.cli.contract import ExitCode, emit, environment_error
from forge.operation.application.build_report.input import BuildReportInput
from forge.operation.application.build_report.output import BuildReportOutput
from forge.operation.application.build_report.use_case import (
    BuildReportUseCase,
    BuildReportUseCaseInterface,
)
from forge.operation.application.operation_reading import OperationUnavailableError
from forge.operation.domain.factory import OperationFactory
from forge.operation.infrastructure.accepted_state import FileAcceptedState
from forge.operation.infrastructure.attempt_results import JsonAttemptResultsReader

FAILURE = "failure"
COMMIT_HINT = (
    "Принятое состояние не закоммичено: закоммитьте эти файлы, указав код и номер задачи "
    "в сообщении коммита"
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Добавить подкоманду `report`."""
    parser = subparsers.add_parser("report", add_help=False)
    parser.add_argument("--operation", required=True)
    parser.set_defaults(handler=run)


def build_use_case() -> BuildReportUseCaseInterface:
    return BuildReportUseCase(
        read_repository(),
        JsonAttemptResultsReader(),
        FileAcceptedState(ACCEPTED_ROOT),
        OperationFactory(),
    )


def run(args: argparse.Namespace, use_case: BuildReportUseCaseInterface | None = None) -> int:
    """`0` — отчёт собран, `1` — операция закрыта со статусом `failure`, `2` — беклог."""
    try:
        output = (use_case or build_use_case()).execute(BuildReportInput(args.operation))
    except OperationUnavailableError as error:
        return environment_error("operation_unavailable", str(error), operation=args.operation)
    emit(report_payload(output))
    return ExitCode.FAILURE if output.operation.status == FAILURE else ExitCode.SUCCESS


def report_payload(output: BuildReportOutput) -> dict[str, Any]:
    """Отчёт в ответе команды."""
    accepted = output.accepted
    return {
        "operation": operation_payload(output.operation),
        "model": output.model,
        "changelog": output.changelog,
        "attempts": [
            {
                "number": a.number,
                "verdict": a.verdict,
                "backlog": a.backlog,
                "directory": a.directory,
                "model": a.model,
                "changelog": a.changelog,
                "reconcile": asdict(a.reconcile) if a.reconcile else None,
                "rollback": asdict(a.rollback) if a.rollback else None,
            }
            for a in output.attempts
        ],
        "backlogs": list(output.backlogs),
        "accepted": asdict(accepted) if accepted else None,
        "commit": (
            {"files": [accepted.model, accepted.changelog, accepted.master], "hint": COMMIT_HINT}
            if accepted
            else None
        ),
    }
