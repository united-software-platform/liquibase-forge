"""Чтение файла модели данных в YAML и проверка его структуры.

Стандартный `safe_load` молча берёт последнее значение повторного ключа, поэтому разборщик
получает дерево узлов загрузчиком `SafeLoader` и обходит его сам: так он видит повторы
и знает логический путь каждого значения (`tables[0].columns[1].length`).

Здесь проверяется только вид значений и состав полей. Смысл — имена, типы, первичный
ключ — проверяет фабрика модели в домене.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from forge.modeling.application.model_reading import DraftReading, ModelUnreadableError
from forge.modeling.domain.data_model import FORMAT_VERSION
from forge.modeling.domain.draft import ColumnDraft, DataModelDraft, TableDraft
from forge.modeling.domain.violation import Violation, join_path

_STR = "tag:yaml.org,2002:str"
_INT = "tag:yaml.org,2002:int"
_BOOL = "tag:yaml.org,2002:bool"

_KIND_NAMES = {
    _STR: "строка",
    _INT: "целое число",
    _BOOL: "логическое значение",
    "tag:yaml.org,2002:float": "дробное число",
    "tag:yaml.org,2002:null": "пустое значение",
    "tag:yaml.org,2002:timestamp": "дата",
}

_ROOT_FIELDS = ("version", "tables")
_TABLE_FIELDS = ("name", "columns", "primary_key")
_COLUMN_REQUIRED = ("name", "type")
_COLUMN_OPTIONAL = ("nullable", "length", "precision", "scale")


class YamlModelDraftReader:
    """Реализация контракта чтения черновика модели для файла YAML."""

    def read(self, path: str) -> DraftReading:
        return parse_model(_read_text(path))


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ModelUnreadableError(path, "файла нет") from None
    except IsADirectoryError:
        raise ModelUnreadableError(path, "это каталог") from None
    except UnicodeDecodeError as error:
        raise ModelUnreadableError(path, f"файл не в кодировке UTF-8: {error.reason}") from None
    except OSError as error:
        raise ModelUnreadableError(path, error.strerror or str(error)) from None


def parse_model(text: str) -> DraftReading:
    """Разобрать текст модели: черновик из таблиц без структурных нарушений и все нарушения."""
    loader = yaml.SafeLoader(text)
    try:
        try:
            root = loader.get_single_node()
        except yaml.MarkedYAMLError as error:
            return _rejected(Violation("", "yaml_syntax", _syntax_message(error)))
        except yaml.YAMLError as error:
            return _rejected(Violation("", "yaml_syntax", f"файл не разбирается как YAML: {error}"))
        return _Walker(loader).model(root)
    finally:
        loader.dispose()


def _rejected(violation: Violation) -> DraftReading:
    return DraftReading(DataModelDraft(()), (violation,))


def _syntax_message(error: yaml.MarkedYAMLError) -> str:
    mark = error.problem_mark
    problem = error.problem or "ошибка синтаксиса"
    if mark is None:
        return f"файл не разбирается как YAML: {problem}"
    position = f"строка {mark.line + 1}, столбец {mark.column + 1}"
    return f"файл не разбирается как YAML: {position}: {problem}"


class _Walker:
    """Обход дерева узлов модели со сбором структурных нарушений по порядку документа."""

    def __init__(self, loader: yaml.SafeLoader) -> None:
        self._loader = loader
        self._violations: list[Violation] = []

    def model(self, root: Node | None) -> DraftReading:
        if root is None:
            self._add(
                "",
                "wrong_kind",
                "файл модели пуст: ожидалось отображение с полями version и tables",
            )
            return self._result(())
        fields = self._mapping(root, "", _ROOT_FIELDS, ())
        if fields is None:
            return self._result(())
        if not self._version(fields.get("version")):
            return self._result(())
        tables_node = fields.get("tables")
        if not isinstance(tables_node, SequenceNode):
            if tables_node is not None:
                self._wrong_kind(tables_node, "tables", "список таблиц")
            return self._result(())
        tables = [self._table(node, position) for position, node in enumerate(tables_node.value)]
        return self._result(tuple(table for table in tables if table is not None))

    def _result(self, tables: tuple[TableDraft, ...]) -> DraftReading:
        return DraftReading(DataModelDraft(tables), tuple(self._violations))

    def _version(self, node: Node | None) -> bool:
        if node is None:
            return False
        if node.tag == _INT and self._integer(node) == FORMAT_VERSION:
            return True
        self._add(
            "version",
            "unsupported_version",
            f"поддерживается только version: {FORMAT_VERSION}, получено {_describe(node)}",
        )
        return False

    def _table(self, node: Node, position: int) -> TableDraft | None:
        path = f"tables[{position}]"
        before = len(self._violations)
        fields = self._mapping(node, path, _TABLE_FIELDS, ())
        if fields is None:
            return None
        name = self._string(fields.get("name"), join_path(path, "name"))
        columns = self._columns(fields.get("columns"), join_path(path, "columns"))
        key = self._names(fields.get("primary_key"), join_path(path, "primary_key"))
        if len(self._violations) > before or name is None or columns is None or key is None:
            return None
        return TableDraft(position, name, columns, key)

    def _columns(self, node: Node | None, path: str) -> tuple[ColumnDraft, ...] | None:
        if node is None:
            return None
        if not isinstance(node, SequenceNode):
            self._wrong_kind(node, path, "список колонок")
            return None
        columns = [self._column(item, f"{path}[{index}]") for index, item in enumerate(node.value)]
        if any(column is None for column in columns):
            return None
        return tuple(column for column in columns if column is not None)

    def _column(self, node: Node, path: str) -> ColumnDraft | None:
        before = len(self._violations)
        fields = self._mapping(node, path, _COLUMN_REQUIRED, _COLUMN_OPTIONAL)
        if fields is None:
            return None
        name = self._string(fields.get("name"), join_path(path, "name"))
        type_name = self._string(fields.get("type"), join_path(path, "type"))
        nullable = self._optional_bool(fields.get("nullable"), join_path(path, "nullable"))
        length, precision, scale = (
            self._optional_int(fields.get(field), join_path(path, field))
            for field in ("length", "precision", "scale")
        )
        if len(self._violations) > before or name is None or type_name is None:
            return None
        return ColumnDraft(name, type_name, nullable, length, precision, scale)

    def _names(self, node: Node | None, path: str) -> tuple[str, ...] | None:
        if node is None:
            return None
        if not isinstance(node, SequenceNode):
            self._wrong_kind(node, path, "список имён колонок")
            return None
        names = [self._string(item, f"{path}[{index}]") for index, item in enumerate(node.value)]
        if any(name is None for name in names):
            return None
        return tuple(name for name in names if name is not None)

    def _mapping(
        self, node: Node, path: str, required: tuple[str, ...], optional: tuple[str, ...]
    ) -> dict[str, Node] | None:
        """Первое вхождение каждого поля; неизвестные, повторные и отсутствующие — нарушения."""
        if not isinstance(node, MappingNode):
            self._wrong_kind(node, path, "отображение с полями " + ", ".join(required))
            return None
        allowed = required + optional
        nodes: dict[str, Node] = {}
        for key_node, value_node in node.value:
            key = key_node.value if isinstance(key_node, ScalarNode) else "?"
            key_path = join_path(path, key)
            if key in nodes:
                self._add(
                    key_path, "duplicate_key", f"ключ {key} повторён, значения не объединяются"
                )
            elif key not in allowed or key_node.tag != _STR:
                self._add(
                    key_path,
                    "unknown_field",
                    f"поле {key} не входит в формат, допустимы: {', '.join(allowed)}",
                )
            else:
                nodes[key] = value_node
        for field in required:
            if field not in nodes:
                self._add(
                    join_path(path, field), "missing_field", f"нет обязательного поля {field}"
                )
        return nodes

    def _string(self, node: Node | None, path: str) -> str | None:
        if node is None:
            return None
        if node.tag == _STR and isinstance(node, ScalarNode):
            return str(node.value)
        self._wrong_kind(node, path, "строка")
        return None

    def _optional_bool(self, node: Node | None, path: str) -> bool | None:
        if node is None:
            return None
        if node.tag == _BOOL and isinstance(node, ScalarNode):
            return bool(self._loader.construct_object(node))
        self._wrong_kind(node, path, "логическое значение true или false")
        return None

    def _optional_int(self, node: Node | None, path: str) -> int | None:
        if node is None:
            return None
        value = self._integer(node) if node.tag == _INT else None
        if value is None:
            self._wrong_kind(node, path, "целое число")
        return value

    def _integer(self, node: Node) -> int | None:
        try:
            value = self._loader.construct_object(node)
        except (yaml.YAMLError, ValueError):
            return None
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def _wrong_kind(self, node: Node, path: str, expected: str) -> None:
        message = f"ожидалось: {expected}; получено: {_describe(node)}"
        if expected == "строка" and node.tag != _STR and isinstance(node, ScalarNode):
            message += f"; чтобы {node.value!r} читалось как строка, возьмите его в кавычки"
        self._add(path, "wrong_kind", message)

    def _add(self, path: str, code: str, message: str) -> None:
        self._violations.append(Violation(path, code, message))


def _describe(node: Node) -> str:
    if isinstance(node, MappingNode):
        return "отображение"
    if isinstance(node, SequenceNode):
        return "список"
    kind = _KIND_NAMES.get(node.tag, f"значение с тегом {node.tag}")
    return f"{kind} {node.value!r}"
