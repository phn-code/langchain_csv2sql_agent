"""The agent's view of Postgres: a catalog read from pg_catalog, and bounded read-only queries."""

import time
from dataclasses import dataclass
from datetime import date, datetime, time as time_of_day
from decimal import Decimal
from typing import Literal, TypedDict
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg_pool import AsyncConnectionPool

type Json = str | int | float | bool | None
type Kind = Literal["number", "temporal", "text"]


class ResultColumn(TypedDict):
    name: str
    kind: Kind


class QueryResult(TypedDict):
    columns: list[ResultColumn]
    rows: list[list[Json]]
    truncated: bool
    elapsed_ms: int


class QueryError(Exception):
    """Postgres rejected the query. The message is written for the model to act on."""


@dataclass(frozen=True)
class CatalogColumn:
    name: str
    type: str
    comment: str | None
    primary_key: bool
    references: str | None


@dataclass(frozen=True)
class CatalogTable:
    name: str
    comment: str | None
    columns: tuple[CatalogColumn, ...]


@dataclass(frozen=True)
class Catalog:
    tables: tuple[CatalogTable, ...]

    @property
    def table_names(self) -> frozenset[str]:
        return frozenset(t.name for t in self.tables)

    def render(self) -> str:
        """DDL with the profile as comments: the format models have seen most often."""
        blocks: list[str] = []
        for table in self.tables:
            lines = [f"-- {table.comment}"] if table.comment else []
            lines.append(f"CREATE TABLE {table.name} (")
            for i, c in enumerate(table.columns):
                constraint = " PRIMARY KEY" if c.primary_key else ""
                constraint += f" REFERENCES {c.references}" if c.references else ""
                comma = "," if i < len(table.columns) - 1 else ""
                comment = f"  -- {c.comment}" if c.comment else ""
                lines.append(f"  {c.name} {c.type}{constraint}{comma}{comment}")
            lines.append(");")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)


_CATALOG_SQL = """
SELECT c.relname, obj_description(c.oid, 'pg_class'), a.attname, format_type(a.atttypid, a.atttypmod),
       col_description(c.oid, a.attnum),
       EXISTS (SELECT 1 FROM pg_constraint p
               WHERE p.conrelid = c.oid AND p.contype = 'p' AND a.attnum = ANY (p.conkey)),
       (SELECT f.confrelid::regclass::text || '(' || fa.attname || ')'
          FROM pg_constraint f JOIN pg_attribute fa ON fa.attrelid = f.confrelid AND fa.attnum = f.confkey[1]
         WHERE f.conrelid = c.oid AND f.contype = 'f' AND f.conkey = ARRAY[a.attnum])
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE n.nspname = %s AND c.relkind IN ('r', 'v', 'm') AND has_table_privilege(c.oid, 'SELECT')
ORDER BY c.relname, a.attnum
"""

_NUMBER_TYPES = {"int2", "int4", "int8", "float4", "float8", "numeric", "oid"}
_TEMPORAL_TYPES = {"date", "timestamp", "timestamptz", "time", "timetz"}


def _kind(type_name: str) -> Kind:
    if type_name in _NUMBER_TYPES:
        return "number"
    return "temporal" if type_name in _TEMPORAL_TYPES else "text"


def _json(value: object) -> Json:
    match value:
        case None | bool() | int() | str():
            return value
        case float():
            return value if value == value and abs(value) != float("inf") else None
        case Decimal():
            return float(value)
        case datetime() | date() | time_of_day():
            return value.isoformat()
        case _:
            return str(value)


def _describe(error: psycopg.Error) -> str:
    diag = error.diag
    parts = [diag.message_primary or str(error)]
    if diag.message_detail:
        parts.append(f"Detail: {diag.message_detail}")
    if diag.message_hint:
        parts.append(f"Hint: {diag.message_hint}")
    return " ".join(parts)


class Database:
    def __init__(self, url: str, *, schema: str = "analytics", max_rows: int, statement_timeout_ms: int):
        self.schema = schema
        self.max_rows = max_rows
        self.statement_timeout_ms = statement_timeout_ms
        self._pool = AsyncConnectionPool(url, min_size=1, max_size=8, open=False)

    async def _open(self) -> AsyncConnectionPool:
        if self._pool.closed:
            await self._pool.open(wait=True, timeout=30)
        return self._pool

    async def close(self) -> None:
        await self._pool.close()

    async def catalog(self) -> Catalog:
        pool = await self._open()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(_CATALOG_SQL, (self.schema,))
            rows = await cur.fetchall()
        tables: dict[str, tuple[str | None, list[CatalogColumn]]] = {}
        for table, table_comment, column, type_name, comment, is_pk, references in rows:
            tables.setdefault(table, (table_comment, []))[1].append(
                CatalogColumn(column, type_name, comment, is_pk, references)
            )
        return Catalog(
            tuple(CatalogTable(name, comment, tuple(columns)) for name, (comment, columns) in tables.items())
        )

    async def query(self, statement: str) -> QueryResult:
        """Run one statement in a read-only transaction, fetching at most `max_rows` rows."""
        started = time.perf_counter()
        pool = await self._open()
        async with pool.connection() as conn:
            try:
                async with conn.transaction():
                    await conn.execute("SET TRANSACTION READ ONLY")
                    await conn.execute(
                        sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(self.statement_timeout_ms))
                    )
                    # A named cursor is a DECLARE, which Postgres only accepts for a single SELECT or VALUES.
                    async with conn.cursor(name=f"q_{uuid4().hex}") as cur:
                        await cur.execute(statement.encode())
                        rows = await cur.fetchmany(self.max_rows + 1)
                        description = cur.description or []
            except psycopg.Error as error:
                raise QueryError(_describe(error)) from error
            columns: list[ResultColumn] = []
            for d in description:
                info = conn.adapters.types.get(d.type_code)
                columns.append({"name": d.name, "kind": _kind(info.name if info else "")})

        return {
            "columns": columns,
            "rows": [[_json(v) for v in row] for row in rows[: self.max_rows]],
            "truncated": len(rows) > self.max_rows,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }
