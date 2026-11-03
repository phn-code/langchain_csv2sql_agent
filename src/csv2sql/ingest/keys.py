"""Infer primary and foreign keys across a set of tables.

Names propose a key and values must prove it. Values alone are not evidence: in the sample data every
customer id is also a transaction id, so pure inclusion-dependency discovery would link the two tables.
"""

from collections.abc import Sequence, Set
from dataclasses import dataclass
from typing import Literal

from csv2sql.ingest.profile import SqlType, Table, Value

KEY_TYPES = (SqlType.BIGINT, SqlType.TEXT)


@dataclass(frozen=True)
class ForeignKey:
    table: str
    column: str
    parent_table: str
    parent_column: str
    offset: int = 0
    """Added to the child value to reach the parent key, for exports that renumbered one side."""
    origin: Literal["name", "ai"] = "name"


@dataclass(frozen=True)
class RejectedKey:
    table: str
    column: str
    parent_table: str
    reason: str


@dataclass(frozen=True)
class Keys:
    primary: dict[str, str]
    foreign: tuple[ForeignKey, ...]
    rejected: tuple[RejectedKey, ...]


def entity(table_name: str) -> str:
    """`sales_customers` -> `customer`: the singular noun a key column would be named after."""
    word = table_name.rsplit("_", 1)[-1]
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _primary_key(table: Table) -> str | None:
    preferred = (f"{entity(table.name)}_id", "id")
    candidates = [
        c
        for c in table.columns
        if (c.name in preferred or c.name.endswith("_id"))
        and c.type in KEY_TYPES
        and c.null_count == 0
        and c.distinct_count == len(table.rows) > 0
    ]
    candidates.sort(key=lambda c: preferred.index(c.name) if c.name in preferred else len(preferred))
    return candidates[0].name if candidates else None


def match_values(child: Set[Value], parent: Set[Value], numeric: bool) -> int | None:
    """The offset that maps every child value onto a parent value, or None."""
    if child <= parent:
        return 0
    if not numeric:
        return None
    offset = min(parent) - min(child)  # type: ignore[operator]
    if all(v + offset in parent for v in child):  # type: ignore[operator]
        return offset
    return None


def infer_keys(tables: Sequence[Table]) -> Keys:
    by_name = {t.name: t for t in tables}
    primary = {t.name: pk for t in tables if (pk := _primary_key(t))}

    foreign: list[ForeignKey] = []
    rejected: list[RejectedKey] = []
    for table in tables:
        for column in table.columns:
            if column.name == primary.get(table.name) or not column.name.endswith("_id"):
                continue
            parents = [
                (name, pk)
                for name, pk in primary.items()
                if name != table.name
                and (column.name == pk or (pk == "id" and column.name == f"{entity(name)}_id"))
                and by_name[name].column(pk).type == column.type
            ]
            matches: list[ForeignKey] = []
            for parent_name, pk in parents:
                child_values = {v for v in table.values(column.name) if v is not None}
                offset = match_values(child_values, set(by_name[parent_name].values(pk)), column.type == SqlType.BIGINT)
                if offset is None:
                    missing = len(child_values - set(by_name[parent_name].values(pk)))
                    rejected.append(
                        RejectedKey(
                            table.name,
                            column.name,
                            parent_name,
                            f"{missing} of {len(child_values)} values have no match, even after shifting",
                        )
                    )
                else:
                    matches.append(ForeignKey(table.name, column.name, parent_name, pk, offset))
            if len(matches) == 1:
                foreign.append(matches[0])
            elif matches:
                rejected.extend(
                    RejectedKey(m.table, m.column, m.parent_table, "ambiguous: several tables match") for m in matches
                )

    return Keys(primary=primary, foreign=tuple(foreign), rejected=tuple(rejected))
