"""Directory in, database out. The directory is the source of truth: every run rebuilds from all of its files."""

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, TypedDict

import psycopg
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from csv2sql.ingest.enrich import Descriptions, enrich
from csv2sql.ingest.keys import Keys, infer_keys
from csv2sql.ingest.load import load
from csv2sql.ingest.profile import Table, read_table
from csv2sql.settings import Settings

log = logging.getLogger(__name__)

SUFFIXES = (".csv", ".tsv", ".txt")


class RejectedRow(TypedDict):
    line: int
    reason: str


class Withheld(TypedDict):
    column: str
    pii: str


class TableReport(TypedDict):
    name: str
    source: str
    rows: int
    primary_key: str | None
    rejected_rows: list[RejectedRow]
    rejected_row_count: int
    withheld: list[Withheld]


class RelationshipReport(TypedDict):
    table: str
    column: str
    parent_table: str
    parent_column: str
    offset: int
    origin: Literal["name", "ai"]


class RejectedRelationship(TypedDict):
    table: str
    column: str
    parent_table: str
    reason: str


class Report(TypedDict):
    tables: list[TableReport]
    relationships: list[RelationshipReport]
    rejected_relationships: list[RejectedRelationship]


def read_directory(directory: Path) -> list[Table]:
    tables: list[Table] = []
    names: set[str] = set()
    for path in sorted((p for p in directory.iterdir() if p.suffix.lower() in SUFFIXES), key=lambda p: p.name.lower()):
        table = read_table(path)
        if not table.columns:
            continue
        name, n = table.name, 1
        while name in names:
            n += 1
            name = f"{table.name}_{n}"
        names.add(name)
        tables.append(
            table if name == table.name else Table(name, table.source, table.columns, table.rows, table.rejected)
        )
    return tables


def build_report(tables: Sequence[Table], keys: Keys) -> Report:
    return {
        "tables": [
            {
                "name": t.name,
                "source": t.source,
                "rows": len(t.rows),
                "primary_key": keys.primary.get(t.name),
                "rejected_rows": [{"line": r.line, "reason": r.reason} for r in t.rejected[:20]],
                "rejected_row_count": len(t.rejected),
                "withheld": [{"column": c.name, "pii": c.pii.value} for c in t.columns if c.pii],
            }
            for t in tables
        ],
        "relationships": [
            {
                "table": f.table,
                "column": f.column,
                "parent_table": f.parent_table,
                "parent_column": f.parent_column,
                "offset": f.offset,
                "origin": f.origin,
            }
            for f in keys.foreign
        ],
        "rejected_relationships": [
            {"table": r.table, "column": r.column, "parent_table": r.parent_table, "reason": r.reason}
            for r in keys.rejected
        ],
    }


def enrichment_model(settings: Settings) -> BaseChatModel | None:
    if not settings.enrich:
        return None
    try:
        return init_chat_model(settings.model)
    except Exception as error:  # a missing API key should not block loading data
        log.warning("AI enrichment disabled: %s", error)
        return None


def ingest(
    directory: Path,
    conn: psycopg.Connection[object] | None,
    *,
    reader_url: str,
    statement_timeout_ms: int,
    model: BaseChatModel | None = None,
) -> Report:
    """Profile every file, infer keys, optionally enrich, then load in one transaction (skipped when conn is None)."""
    tables = read_directory(directory)
    keys = infer_keys(tables)
    descriptions = Descriptions()
    if model is not None and tables:
        try:
            keys, descriptions = enrich(model, tables, keys)
        except Exception:
            log.exception("AI enrichment failed; loading with inferred keys only")
    if conn is not None:
        load(conn, tables, keys, reader_url, statement_timeout_ms, descriptions)
    return build_report(tables, keys)
