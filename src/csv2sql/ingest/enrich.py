"""Optional AI pass over the profiles: plain-English descriptions and relationships the name rules missed.

The model proposes and the data decides. A proposed relationship is kept only if it targets a primary key, the
types match, and every child value appears in the parent (allowing a constant shift), the same proof the name
rules must pass. Sample values of columns flagged as personal data are never sent to the model.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from csv2sql.ingest.keys import ForeignKey, Keys, RejectedKey, match_values
from csv2sql.ingest.profile import SqlType, Table


class ColumnNote(BaseModel):
    name: str
    description: str = Field(description="One sentence: what the column means, with units if evident.")


class TableNote(BaseModel):
    name: str
    description: str = Field(description="One sentence: what one row of the table represents.")
    columns: list[ColumnNote]


class Proposal(BaseModel):
    table: str
    column: str
    parent_table: str
    parent_column: str = Field(description="Must be the parent table's primary key.")


class Enrichment(BaseModel):
    tables: list[TableNote]
    relationships: list[Proposal] = Field(
        description="Foreign keys that are likely but absent from `known_relationships`. Empty if none."
    )


@dataclass(frozen=True)
class Descriptions:
    tables: dict[str, str] = field(default_factory=dict[str, str])
    columns: dict[tuple[str, str], str] = field(default_factory=dict[tuple[str, str], str])


_PROMPT = """You are documenting a database that was loaded from CSV files, for an analyst who will query it.
For every table and column, write a short, factual description based on the names and profile below.
Then list foreign keys that are likely but missing from known_relationships, for example a column named after a
synonym of another table. Only propose a parent column that is that table's primary key. Do not guess wildly:
each proposal is checked against the data and rejected unless every value matches.

{profiles}"""


def _profiles(tables: Sequence[Table], keys: Keys) -> str:
    def column(table: Table, name: str) -> dict[str, object]:
        c = table.column(name)
        info: dict[str, object] = {"name": c.name, "type": c.type.value, "distinct": c.distinct_count}
        if c.pii:
            info["personal_data"] = c.pii.value
        elif c.categories:
            info["values"] = list(c.categories)
        else:
            info["examples"] = [str(v)[:60] for v in dict.fromkeys(table.values(c.name)) if v is not None][:3]
        if c.minimum is not None:
            info["range"] = [str(c.minimum), str(c.maximum)]
        return info

    return json.dumps(
        {
            "tables": [
                {
                    "name": t.name,
                    "source": t.source,
                    "rows": len(t.rows),
                    "primary_key": keys.primary.get(t.name),
                    "columns": [column(t, c.name) for c in t.columns],
                }
                for t in tables
            ],
            "known_relationships": [
                f"{f.table}.{f.column} -> {f.parent_table}.{f.parent_column}" for f in keys.foreign
            ],
        },
        indent=1,
    )


def _verify(proposal: Proposal, tables: dict[str, Table], keys: Keys) -> ForeignKey | RejectedKey:
    def reject(reason: str) -> RejectedKey:
        return RejectedKey(proposal.table, proposal.column, proposal.parent_table, f"AI suggestion rejected: {reason}")

    child, parent = tables.get(proposal.table), tables.get(proposal.parent_table)
    if child is None or parent is None or child is parent:
        return reject("unknown table")
    if keys.primary.get(parent.name) != proposal.parent_column:
        return reject(f"{proposal.parent_column} is not the primary key of {parent.name}")
    try:
        child_column, parent_column = child.column(proposal.column), parent.column(proposal.parent_column)
    except StopIteration:
        return reject("unknown column")
    if child_column.type != parent_column.type:
        return reject(f"type {child_column.type} does not match {parent_column.type}")
    child_values = {v for v in child.values(child_column.name) if v is not None}
    offset = match_values(child_values, set(parent.values(parent_column.name)), child_column.type == SqlType.BIGINT)
    if offset is None:
        return reject("values do not match")
    return ForeignKey(child.name, child_column.name, parent.name, parent_column.name, offset, origin="ai")


def enrich(model: BaseChatModel, tables: Sequence[Table], keys: Keys) -> tuple[Keys, Descriptions]:
    structured = model.with_structured_output(Enrichment)
    result = structured.invoke(_PROMPT.format(profiles=_profiles(tables, keys)))
    assert isinstance(result, Enrichment)

    by_name = {t.name: t for t in tables}
    known = {(f.table, f.column) for f in keys.foreign}
    foreign, rejected = list(keys.foreign), list(keys.rejected)
    for proposal in result.relationships:
        if (proposal.table, proposal.column) in known:
            continue
        verdict = _verify(proposal, by_name, keys)
        if isinstance(verdict, ForeignKey):
            foreign.append(verdict)
            known.add((verdict.table, verdict.column))
        else:
            rejected.append(verdict)

    descriptions = Descriptions(
        tables={n.name: n.description for n in result.tables if n.name in by_name},
        columns={(n.name, c.name): c.description for n in result.tables if n.name in by_name for c in n.columns},
    )
    return Keys(keys.primary, tuple(foreign), tuple(rejected)), descriptions
