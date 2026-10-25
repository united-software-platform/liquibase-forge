"""Пример `reconcile.json` из `docs/seed-reconciliation.md` совпадает с ответом команды."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

import pytest

from forge.cli.commands import reconcile_seed
from forge.shared.infrastructure.json_result_writer import JsonResultWriter
from tests.seeding.fakes import FakeDatabase, use_case
from tests.seeding.support import MIGRATION_EXAMPLE

DOCUMENT = Path(__file__).resolve().parents[2] / "docs" / "seed-reconciliation.md"
ATTEMPT = Path("backlog/forge-seed/20261025-101500/attempt-1")

# Строки БД примера: `draft` с прежним заголовком, `new` не вставлена, `archived` не удалена
ROWS = """version: 1
tables:
  - name: status_group
    rows:
      - {code: active, title: Активные}
      - {code: closed, title: Закрытые}
  - name: order_status
    rows:
      - {code: archived, group_code: active, title: Архив, fee: "0.00"}
      - {code: draft, group_code: active, title: Черновик}
      - {code: paid, group_code: closed, title: Оплачен, fee: "12.5"}
"""


def _example() -> object:
    text = DOCUMENT.read_text(encoding="utf-8")
    section = text.split("\n## Файл reconcile.json\n", 1)[1].split("\n## ", 1)[0]
    (block,) = re.findall(r"```json\n(.*?)```", section, re.S)
    return json.loads(block)


def test_document_example_matches_command_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ATTEMPT).mkdir(parents=True)
    shutil.copyfile(MIGRATION_EXAMPLE / "attempt.yaml", tmp_path / ATTEMPT / "seed.yaml")
    args = argparse.Namespace(
        seed=str(ATTEMPT / "seed.yaml"),
        changelog=str(ATTEMPT / "changelog.yaml"),
        accepted_seed=str(MIGRATION_EXAMPLE / "accepted.yaml"),
        model=str(MIGRATION_EXAMPLE / "model.yaml"),
    )

    code = reconcile_seed.run(args, use_case(tmp_path, FakeDatabase(ROWS), JsonResultWriter()))

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload == _example()
    assert (
        json.loads((tmp_path / ATTEMPT / "reconcile.json").read_text(encoding="utf-8")) == payload
    )


def test_document_links_lead_to_existing_files() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")

    for target in re.findall(r"\]\(\./([^)#]+)", text):
        assert (DOCUMENT.parent / target).is_file(), target
