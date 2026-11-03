"""Read one CSV file into a typed, profiled table."""

import csv
import io
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


# Postgres reserved and type-function keywords (pg_get_keywords catcode R and T). A model writing SQL will not
# quote them, so names that collide get a trailing underscore instead.
_KEYWORDS = frozenset(
    [
        "all",
        "analyse",
        "analyze",
        "and",
        "any",
        "array",
        "as",
        "asc",
        "asymmetric",
        "authorization",
        "binary",
        "both",
        "case",
        "cast",
        "check",
        "collate",
        "collation",
        "column",
        "concurrently",
        "constraint",
        "create",
        "cross",
        "current_catalog",
        "current_date",
        "current_role",
        "current_schema",
        "current_time",
        "current_timestamp",
        "current_user",
        "default",
        "deferrable",
        "desc",
        "distinct",
        "do",
        "else",
        "end",
        "except",
        "false",
        "fetch",
        "for",
        "foreign",
        "freeze",
        "from",
        "full",
        "grant",
        "group",
        "having",
        "ilike",
        "in",
        "initially",
        "inner",
        "intersect",
        "into",
        "is",
        "isnull",
        "join",
        "lateral",
        "leading",
        "left",
        "like",
        "limit",
        "localtime",
        "localtimestamp",
        "natural",
        "not",
        "notnull",
        "null",
        "offset",
        "on",
        "only",
        "or",
        "order",
        "outer",
        "overlaps",
        "placing",
        "primary",
        "references",
        "returning",
        "right",
        "select",
        "session_user",
        "similar",
        "some",
        "symmetric",
        "system_user",
        "table",
        "tablesample",
        "then",
        "to",
        "trailing",
        "true",
        "union",
        "unique",
        "user",
        "using",
        "variadic",
        "verbose",
        "when",
        "where",
        "window",
        "with",
    ]
)
_MAX_IDENTIFIER = 63


def snake_case(name: str) -> str:
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name.strip())
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()[:_MAX_IDENTIFIER]
    if not name:
        return "column"
    if name[0].isdigit():
        name = f"_{name}"
    return f"{name}_" if name in _KEYWORDS else name


def _unique_names(names: Sequence[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        result.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return result


_INTEGER = re.compile(r"[+-]?[$€£]?(0|[1-9]\d{0,2}(,\d{3})+|[1-9]\d*)")
_FLOAT = re.compile(r"[+-]?[$€£]?([1-9]\d{0,2}(,\d{3})+(\.\d*)?|(0|[1-9]\d*)(\.\d*)?|\.\d+)([eE][+-]?\d+)?")
_NUMBER_NOISE = str.maketrans("", "", "$€£,")
_BOOLEANS = {
    "true": True,
    "t": True,
    "yes": True,
    "y": True,
    "false": False,
    "f": False,
    "no": False,
    "n": False,
}
_INT64 = 2**63


def _parse_int(text: str) -> int:
    if not _INTEGER.fullmatch(text) or abs(value := int(text.translate(_NUMBER_NOISE))) >= _INT64:
        raise ValueError(text)
    return value


def _parse_float(text: str) -> float:
    if not _FLOAT.fullmatch(text):
        raise ValueError(text)
    return float(text.translate(_NUMBER_NOISE))


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


def _strptime(*formats: str, keep_time: bool) -> Callable[[str], Value]:
    def parse(text: str) -> Value:
        for fmt in formats:
            try:
                parsed = datetime.strptime(text, fmt)
            except ValueError:
                continue
            return parsed if keep_time else parsed.date()
        raise ValueError(text)

    return parse


# Tried in order; the first parser that accepts every non-empty value wins. Slash dates try month-first, so a
# column is read day-first only when some value rules month-first out (a first component above 12).
_PARSERS: tuple[tuple[SqlType, Callable[[str], Value]], ...] = (
    (SqlType.BIGINT, _parse_int),
    (SqlType.DOUBLE, _parse_float),
    (SqlType.BOOLEAN, _parse_bool),
    (SqlType.DATE, _parse_date),
    (SqlType.TIMESTAMPTZ, _parse_timestamp),
    (SqlType.DATE, _strptime("%m/%d/%Y", "%Y/%m/%d", keep_time=False)),
    (SqlType.DATE, _strptime("%d/%m/%Y", keep_time=False)),
    (SqlType.TIMESTAMPTZ, _strptime("%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", keep_time=True)),
    (SqlType.TIMESTAMPTZ, _strptime("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", keep_time=True)),
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


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _delimiter(text: str) -> str:
    """The candidate that splits the header line most. Headers rarely hold quoted text, unlike data rows."""
    header = text.split("\n", 1)[0]
    return max(",;\t|", key=header.count) if any(d in header for d in ",;\t|") else ","


def read_table(path: Path) -> Table:
    text = _decode(path.read_bytes())
    with io.StringIO(text, newline="") as f:
        reader = csv.reader(f, delimiter=_delimiter(text))
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
