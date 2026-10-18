"""Принятое состояние проекта в `db/`: модель, changelog операций и `master.yaml`."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import yaml

from forge.operation.application.accepted_state import AcceptanceError, AcceptedFiles

MODEL = "model.yaml"
CHANGELOG = "changelog.yaml"
MASTER = "master.yaml"


class FileAcceptedState:
    """Реализация принятого состояния: файлы в каталоге `db/` корня проекта.

    `include` в `master.yaml` указывает файл относительно самого `master.yaml`: так Liquibase
    находит его при любом каталоге поиска, а `logicalFilePath` changeset уже задан в файле.
    """

    def __init__(self, root: Path = Path("db")) -> None:
        self._root = root

    def files(self, stamp: str) -> AcceptedFiles:
        changelog = self._root / "changelog"
        return AcceptedFiles(
            model=(self._root / MODEL).as_posix(),
            changelog=(changelog / f"{stamp}.yaml").as_posix(),
            master=(changelog / MASTER).as_posix(),
        )

    def accept(self, stamp: str, attempt_directory: str) -> AcceptedFiles:
        files = self.files(stamp)
        source = Path(attempt_directory)
        for name in (MODEL, CHANGELOG):
            if not (source / name).is_file():
                raise AcceptanceError(f"в каталоге попытки {attempt_directory} нет {name}")
        try:
            Path(files.changelog).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / MODEL, files.model)
            shutil.copyfile(source / CHANGELOG, files.changelog)
            self._include(Path(files.master), f"{stamp}.yaml")
        except OSError as error:
            raise AcceptanceError(f"принять в {self._root} не удалось: {error}") from None
        return files

    @staticmethod
    def _include(master: Path, file: str) -> None:
        document: dict[str, Any] = {"databaseChangeLog": []}
        if master.is_file():
            loaded = yaml.safe_load(master.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or not isinstance(
                loaded.get("databaseChangeLog") or [], list
            ):
                raise AcceptanceError(f"{master} не в формате master-changelog")
            document = {"databaseChangeLog": loaded.get("databaseChangeLog") or []}
        entries: list[Any] = document["databaseChangeLog"]
        if any(isinstance(e, dict) and e.get("include", {}).get("file") == file for e in entries):
            return
        entries.append({"include": {"file": file, "relativeToChangelogFile": True}})
        header = "# Принятые changelog операций по порядку принятия: ведёт forge close\n"
        body = yaml.safe_dump(document, allow_unicode=True, sort_keys=False)
        draft = master.with_name(master.name + ".tmp")
        draft.write_text(header + body, encoding="utf-8")
        os.replace(draft, master)
