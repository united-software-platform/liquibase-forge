"""Команда `forge generate`: changelog из добавляющей разницы моделей."""

from __future__ import annotations

import argparse
import os
from typing import Any

from forge.cli.contract import ExitCode, emit, environment_error
from forge.migration.application.generate_changelog.input import GenerateChangelogInput
from forge.migration.application.generate_changelog.output import GenerateChangelogOutput
from forge.migration.application.generate_changelog.use_case import (
    AcceptedModelError,
    GenerateChangelogUseCase,
    GenerateChangelogUseCaseInterface,
)
from forge.migration.application.operation_record import OperationRecordUnavailableError
from forge.migration.domain.additive_diff import AdditiveDiff
from forge.migration.infrastructure.liquibase_changelog import LiquibaseYamlChangelogWriter
from forge.migration.infrastructure.operation_record_reader import (
    FrontmatterOperationRecordReader,
)
from forge.modeling.application.load_model.use_case import LoadModelUseCase
from forge.modeling.application.model_reading import ModelUnreadableError
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader
from forge.shared.application.settings import SettingsUnavailableError
from forge.shared.infrastructure.settings import EnvironmentSettings

ACCEPTED_MODEL = "model.yaml"


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Добавить подкоманду `generate`."""
    parser = subparsers.add_parser("generate", add_help=False)
    parser.add_argument("--model", required=True)
    # Без `--accepted` принятая модель берётся из корня принятого состояния
    parser.add_argument("--accepted")
    parser.add_argument("--operation", required=True)
    parser.add_argument("--out", required=True)
    parser.set_defaults(handler=run)


def build_use_case() -> GenerateChangelogUseCaseInterface:
    """Собрать сценарий с чтением беклога, загрузкой моделей и записью YAML Liquibase."""
    return GenerateChangelogUseCase(
        FrontmatterOperationRecordReader(),
        LoadModelUseCase(YamlModelDraftReader(), DataModelFactory()),
        LiquibaseYamlChangelogWriter(),
        AdditiveDiff(),
    )


def run(args: argparse.Namespace, use_case: GenerateChangelogUseCaseInterface | None = None) -> int:
    """`0` — changelog записан, `1` — модель некорректна или неаддитивна, `2` — окружение."""
    try:
        accepted = args.accepted or _accepted_model()
    except SettingsUnavailableError as error:
        return environment_error("accepted_root_invalid", str(error), operation=args.operation)
    request = GenerateChangelogInput(args.model, accepted, args.operation, args.out)
    try:
        output = (use_case or build_use_case()).execute(request)
    except OperationRecordUnavailableError as error:
        return environment_error("operation_unavailable", str(error), operation=args.operation)
    except ModelUnreadableError as error:
        return environment_error("model_unreadable", str(error), model=error.path)
    except AcceptedModelError as error:
        return environment_error("accepted_model_invalid", str(error), accepted=accepted)
    emit(_payload(output))
    return ExitCode.SUCCESS if output.generated else ExitCode.FAILURE


def _accepted_model() -> str:
    return (EnvironmentSettings(os.environ).accepted_root() / ACCEPTED_MODEL).as_posix()


def _payload(output: GenerateChangelogOutput) -> dict[str, Any]:
    return {
        "changelog": output.changelog_path,
        "logical_file_path": output.logical_file_path,
        "changesets": [
            {"id": c.id, "kind": c.kind, "table": c.table, "column": c.column}
            for c in output.changesets
        ],
        "violations": [
            {"path": v.path, "code": v.code, "message": v.message} for v in output.violations
        ],
        "non_additive": [
            {"code": c.code, "table": c.table, "column": c.column, "message": c.message}
            for c in output.non_additive
        ],
    }
