"""Read one CSV file into a typed, profiled table."""

import csv
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

type Value = int | float | bool | datetime | date | str | None


class SqlType(StrEnum):
    BIGINT = "bigint"
    DOUBLE = "double precision"
    BOOLEAN = "boolean"
    DATE = "date"
    TIMESTAMPTZ = "timestamptz"
    TEXT = "text"


class Pii(StrEnum):
    EMAIL = "email address"
    PHONE = "phone number"
    PERSON_NAME = "person name"
    STREET_ADDRESS = "street address"
    CARD_NUMBER = "payment card number"


@dataclass(frozen=True)
class Column:
    name: str
    source_name: str
    type: SqlType
    null_count: int
    distinct_count: int
    minimum: Value
    maximum: Value
    categories: tuple[str, ...] | None
    pii: Pii | None


@dataclass(frozen=True)
class Rejection:
    line: int
    reason: str


@dataclass(frozen=True)
class Table:
    name: str
    source: str
    columns: tuple[Column, ...]
    rows: list[tuple[Value, ...]]
    rejected: tuple[Rejection, ...]

    def column(self, name: str) -> Column:
        return next(c for c in self.columns if c.name == name)

    def values(self, name: str) -> list[Value]:
        index = [c.name for c in self.columns].index(name)
        return [row[index] for row in self.rows]


MAX_CATEGORIES = 12


def snake_case(name: str) -> str:
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name.strip())
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    if not name:
        return "column"
    return f"_{name}" if name[0].isdigit() else name


def _unique_names(names: Sequence[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        result.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return result


_INTEGER = re.compile(r"[+-]?(0|[1-9]\d*)")
_FLOAT = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
_BOOLEANS = {"true": True, "t": True, "yes": True, "y": True, "false": False, "f": False, "no": False, "n": False}
_INT64 = 2**63


def _parse_int(text: str) -> int:
    if not _INTEGER.fullmatch(text) or abs(int(text)) >= _INT64:
        raise ValueError(text)
    return int(text)


def _parse_float(text: str) -> float:
    if not _FLOAT.fullmatch(text):
        raise ValueError(text)
    return float(text)


def _parse_bool(text: str) -> bool:
    return _BOOLEANS[text.lower()]


def _parse_date(text: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError(text)
    return date.fromisoformat(text)


def _parse_timestamp(text: str) -> datetime:
    if not re.match(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", text):
        raise ValueError(text)
    return datetime.fromisoformat(text)


# Tried in order; the first parser that accepts every non-empty value wins.
_PARSERS: tuple[tuple[SqlType, Callable[[str], Value]], ...] = (
    (SqlType.BIGINT, _parse_int),
    (SqlType.DOUBLE, _parse_float),
    (SqlType.BOOLEAN, _parse_bool),
    (SqlType.DATE, _parse_date),
    (SqlType.TIMESTAMPTZ, _parse_timestamp),
)


def _infer_type(texts: Sequence[str]) -> tuple[SqlType, list[Value]]:
    present = [t for t in texts if t]
    for sql_type, parse in _PARSERS:
        if not present:
            break
        try:
            parsed = {t: parse(t) for t in set(present)}
        except (ValueError, KeyError):
            continue
        return sql_type, [parsed[t] if t else None for t in texts]
    return SqlType.TEXT, [t or None for t in texts]


_PII_NAMES: dict[Pii, re.Pattern[str]] = {
    Pii.EMAIL: re.compile(r"(^|_)e_?mail(_|$)"),
    Pii.PHONE: re.compile(r"(^|_)(phone|mobile|fax|telephone)(_|$)"),
    Pii.PERSON_NAME: re.compile(r"^(first|last|middle|full|given|family|sur)_?name$"),
    Pii.STREET_ADDRESS: re.compile(r"^(street_|home_|mailing_)?address(_line)?(_?\d)?$|^street$"),
    Pii.CARD_NUMBER: re.compile(r"(^|_)(card_?(number|num|no)|credit_card|pan)(_|$)"),
}
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.IGNORECASE)


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def _detect_pii(name: str, texts: Sequence[str]) -> Pii | None:
    for kind, pattern in _PII_NAMES.items():
        if pattern.search(name):
            return kind
    present = [t for t in texts if t]
    if not present:
        return None

    def mostly(test: Callable[[str], bool]) -> bool:
        return sum(map(test, present)) >= 0.9 * len(present)

    if mostly(lambda t: bool(_EMAIL.fullmatch(t))):
        return Pii.EMAIL
    if mostly(lambda t: t.isdigit() and 13 <= len(t) <= 19 and _luhn(t)):
        return Pii.CARD_NUMBER
    return None


def _profile(name: str, source_name: str, texts: Sequence[str]) -> tuple[Column, list[Value]]:
    sql_type, values = _infer_type(texts)
    present = [v for v in values if v is not None]
    distinct = set(present)
    ordered = sql_type not in (SqlType.TEXT, SqlType.BOOLEAN) and bool(present)
    categories = None
    if sql_type in (SqlType.TEXT, SqlType.BOOLEAN) and len(distinct) <= MAX_CATEGORIES < len(present):
        categories = tuple(sorted(map(str, distinct)))
    column = Column(
        name=name,
        source_name=source_name,
        type=sql_type,
        null_count=len(values) - len(present),
        distinct_count=len(distinct),
        minimum=min(present) if ordered else None,  # type: ignore[type-var]
        maximum=max(present) if ordered else None,  # type: ignore[type-var]
        categories=categories,
        pii=_detect_pii(name, texts),
    )
    return column, values


def _section_layout(record: Sequence[str], names: Sequence[str]) -> list[int] | None:
    """Where each cell of a repeated or partial header row belongs, if `record` is one.

    Concatenated exports restart with their own header, sometimes with fewer or reordered columns.
    """
    cells = [snake_case(cell) for cell in record]
    if len(cells) < 2 or len(set(cells)) != len(cells) or not set(cells) <= set(names):
        return None
    return [names.index(cell) for cell in cells]


def read_table(path: Path) -> Table:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            raise ValueError(f"{path.name} is empty")
        names = _unique_names([snake_case(h) for h in header])
        layout = list(range(len(names)))
        records: list[list[str]] = []
        rejected: list[Rejection] = []
        for record in reader:
            line = reader.line_num
            if not any(cell.strip() for cell in record):
                continue
            if (section := _section_layout(record, names)) is not None:
                layout = section
            elif len(record) != len(layout):
                rejected.append(Rejection(line, f"expected {len(layout)} fields, found {len(record)}"))
            else:
                row = [""] * len(names)
                for position, cell in zip(layout, record, strict=True):
                    row[position] = cell.strip()
                records.append(row)

    columns: list[Column] = []
    column_values: list[list[Value]] = []
    for i, (name, source_name) in enumerate(zip(names, header, strict=True)):
        column, values = _profile(name, source_name.strip(), [r[i] for r in records])
        columns.append(column)
        column_values.append(values)

    return Table(
        name=snake_case(path.stem),
        source=path.name,
        columns=tuple(columns),
        rows=list(zip(*column_values, strict=True)) if columns else [],
        rejected=tuple(rejected),
    )
