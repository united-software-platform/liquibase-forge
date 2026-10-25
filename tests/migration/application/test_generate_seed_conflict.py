"""Сценарий построения changelog против принятого seed: виды `seed_conflict` и их отсутствие."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.migration.application.generate_changelog.input import GenerateChangelogInput
from forge.migration.application.generate_changelog.output import GenerateChangelogOutput
from forge.migration.application.generate_changelog.use_case import GenerateChangelogUseCase
from forge.migration.application.seed_conflicts import AcceptedSeedError
from forge.migration.domain.model_diff import ModelDiff
from forge.migration.infrastructure.liquibase_changelog import LiquibaseConstraintNaming
from forge.migration.infrastructure.seed_conflicts import SeedConflictChecker
from forge.modeling.application.load_model.use_case import LoadModelUseCase
from forge.modeling.domain.factory import DataModelFactory
from forge.modeling.infrastructure.yaml_reader import YamlModelDraftReader
from forge.seeding.domain.factory import SeedFactory
from forge.seeding.infrastructure.yaml_reader import YamlSeedDraftReader
from tests.migration.application.test_generate_changelog import _Operations, _Writer

GROUP = """
  - name: status_group
    columns:
      - {name: code, type: string, length: 16}
    primary_key: [code]
"""

STATUS = """
  - name: order_status
    columns:
      - {name: code, type: string, length: 32}
      - {name: title, type: text, nullable: false}
      - {name: color, type: text}
@extra@    primary_key: [code]
@constraints@"""

SEED = """version: 1
tables:
  - name: order_status
    rows:
      - {code: draft, title: Черновик, color: grey}
      - {code: paid, title: Черновик}
"""


def _status(extra: str = "", constraints: str = "", without_color: bool = False) -> str:
    text = STATUS.replace("@extra@", extra).replace("@constraints@", constraints)
    return text.replace("      - {name: color, type: text}\n", "") if without_color else text


def _run(
    tmp_path: Path,
    attempt: str,
    seed: str | None = SEED,
    accepted: str = _status(),
    writer: _Writer | None = None,
) -> GenerateChangelogOutput:
    model = tmp_path / "model.yaml"
    model.write_text("version: 1\ntables:\n" + attempt, encoding="utf-8")
    accepted_model = tmp_path / "accepted.yaml"
    accepted_model.write_text("version: 1\ntables:\n" + accepted, encoding="utf-8")
    seed_path = tmp_path / "seed.yaml"
    if seed is not None:
        seed_path.write_text(seed, encoding="utf-8")
    use_case = GenerateChangelogUseCase(
        _Operations(),
        LoadModelUseCase(YamlModelDraftReader(), DataModelFactory()),
        writer or _Writer(),
        ModelDiff(),
        LiquibaseConstraintNaming(),
        SeedConflictChecker(YamlSeedDraftReader(), SeedFactory()),
    )
    return use_case.execute(
        GenerateChangelogInput(
            str(model), str(accepted_model), "op/tasks.md", "out/changelog.yaml", str(seed_path)
        )
    )


def _kinds(output: GenerateChangelogOutput) -> list[tuple[str, str, str | None]]:
    return [(c.kind, c.table, c.column) for c in output.seed_conflict]


def test_dropped_seeded_table(tmp_path: Path) -> None:
    writer = _Writer()

    output = _run(tmp_path, GROUP, accepted=GROUP + _status(), writer=writer)

    assert (output.generated, output.changelog_path) == (False, None)
    assert _kinds(output) == [("seeded_table_dropped", "order_status", None)]
    assert writer.written == {} and writer.removed == ["out/changelog.yaml"]


def test_not_null_column_in_seeded_table(tmp_path: Path) -> None:
    extra = "      - {name: sort_order, type: integer, nullable: false}\n"

    output = _run(tmp_path, _status(extra=extra))

    assert output.generated is False
    assert set(_kinds(output)) == {("not_null_column_added", "order_status", "sort_order")}


def test_not_null_column_in_empty_seeded_table(tmp_path: Path) -> None:
    extra = "      - {name: sort_order, type: integer, nullable: false}\n"
    empty = "version: 1\ntables:\n  - name: order_status\n    rows: []\n"

    output = _run(tmp_path, _status(extra=extra), seed=empty)

    assert (output.generated, output.seed_conflict) == (True, ())


def test_unique_violated_by_seed(tmp_path: Path) -> None:
    output = _run(tmp_path, _status(constraints="    unique:\n      - [title]\n"))

    assert output.generated is False
    assert _kinds(output) == [("unique_violated_by_seed", "order_status", None)]
    assert "title" in output.seed_conflict[0].message


def test_foreign_key_to_table_outside_seed(tmp_path: Path) -> None:
    extra = "      - {name: group_code, type: string, length: 16}\n"
    key = (
        "    foreign_keys:\n"
        "      - columns: [group_code]\n"
        "        references: {table: status_group, columns: [code]}\n"
    )

    output = _run(
        tmp_path, GROUP + _status(extra=extra, constraints=key), accepted=GROUP + _status()
    )

    assert _kinds(output) == [("foreign_key_violated_by_seed", "order_status", None)]


def test_dropped_seeded_column_is_not_a_conflict(tmp_path: Path) -> None:
    writer = _Writer()

    output = _run(tmp_path, _status(without_color=True), writer=writer)

    assert (output.generated, output.seed_conflict) == (True, ())
    assert list(writer.written) == ["out/changelog.yaml"]


def test_without_accepted_seed_there_is_no_check(tmp_path: Path) -> None:
    output = _run(tmp_path, GROUP, seed=None, accepted=GROUP + _status())

    assert (output.generated, output.seed_conflict) == (True, ())


def test_unreadable_accepted_seed(tmp_path: Path) -> None:
    (tmp_path / "seed.yaml").mkdir()

    with pytest.raises(AcceptedSeedError):
        _run(tmp_path, _status(), seed=None)
