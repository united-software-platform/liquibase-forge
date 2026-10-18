"""Входной контракт сценария построения changelog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenerateChangelogInput:
    """Модель попытки, принятая модель, беклог операции и путь changelog."""

    model_path: str
    accepted_path: str
    operation_path: str
    out_path: str
