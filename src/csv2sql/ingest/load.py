"""Write profiled tables to Postgres.

`raw` holds every column, typed. `analytics` is what the agent sees: personal data is left out, key shifts are
corrected, primary and foreign keys are real constraints, and each column's profile is its COMMENT. A read-only
role gets SELECT on `analytics` and nothing else, so the database itself enforces what the agent may read.
"""

from collections.abc import Sequence
from datetime import date, datetime

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from csv2sql.ingest.keys import Keys
from csv2sql.ingest.profile import Column, SqlType, Table, Value

RAW = "raw"
ANALYTICS = "analytics"


def _format(value: Value) -> str:
    match value:
        case datetime():
            return value.isoformat(sep=" ", timespec="seconds")
        case date():
            return value.isoformat()
        case float():
            return f"{value:g}"
        case int():
            return f"{value:,}"
        case _:
            return repr(value)


def _quote(text: str, limit: int = 60) -> str:
    return "'" + (text if len(text) <= limit else text[: limit - 1] + "…").replace("'", "''") + "'"


def describe_column(column: Column, rows: int, shift: tuple[int, str] | None) -> str:
    notes = [f"From CSV column {column.source_name}."]
    lo, hi = column.minimum, column.maximum
    if shift and isinstance(lo, int) and isinstance(hi, int):
        lo, hi = lo + shift[0], hi + shift[0]
    if column.categories is not None:
        notes.append("One of: " + ", ".join(_quote(c) for c in column.categories) + ".")
    elif lo is not None:
        notes.append(f"Range {_format(lo)} to {_format(hi)}.")
    if column.type == SqlType.TEXT and column.categories is None:
        notes.append(f"{column.distinct_count:,} distinct values.")
    if column.null_count:
        notes.append(f"{column.null_count / rows:.0%} null.")
    if shift:
        offset, parent = shift
        notes.append(f"Shifted by {offset:+,} from the source file to match {parent}.")
    return " ".join(notes)


def describe_table(table: Table, withheld: Sequence[Column]) -> str:
    notes = [f"Loaded from {table.source}: {len(table.rows):,} rows."]
    if table.rejected:
        notes.append(f"{len(table.rejected)} malformed rows skipped.")
    if withheld:
        notes.append(
            "Withheld for privacy: " + ", ".join(f"{c.name} ({c.pii})" for c in withheld) + "."
        )
    return " ".join(notes)


def _ensure_reader(cur: psycopg.Cursor[object], reader_url: str, statement_timeout_ms: int) -> str:
    params = conninfo_to_dict(reader_url)
    role, password = str(params["user"]), str(params.get("password", ""))
    exists = cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
    verb = sql.SQL("ALTER") if exists else sql.SQL("CREATE")
    cur.execute(
        sql.SQL("{} ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}").format(
            verb, sql.Identifier(role), sql.Literal(password)
        )
    )
    ident = sql.Identifier(role)
    for setting, value in (
        ("default_transaction_read_only", "on"),
        ("statement_timeout", str(statement_timeout_ms)),
        ("idle_in_transaction_session_timeout", "10000"),
        ("search_path", ANALYTICS),
    ):
        cur.execute(sql.SQL("ALTER ROLE {} SET {} = {}").format(ident, sql.Identifier(setting), sql.Literal(value)))
    cur.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM {}").format(ident))
    database = sql.Identifier(str(cur.execute("SELECT current_database()").fetchone()[0]))  # type: ignore[index]
    cur.execute(sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC").format(database))
    cur.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(ANALYTICS), ident))
    cur.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(sql.Identifier(ANALYTICS), ident))
    return role


def load(
    conn: psycopg.Connection[object],
    tables: Sequence[Table],
    keys: Keys,
    reader_url: str,
    statement_timeout_ms: int,
) -> None:
    shifts = {(fk.table, fk.column): fk for fk in keys.foreign if fk.offset}
    with conn.transaction(), conn.cursor() as cur:
        for schema in (RAW, ANALYTICS):
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

        for table in tables:
            raw = sql.Identifier(RAW, table.name)
            cur.execute(
                sql.SQL("CREATE TABLE {} ({})").format(
                    raw,
                    sql.SQL(", ").join(
                        sql.SQL("{} {}").format(sql.Identifier(c.name), sql.SQL(c.type.value)) for c in table.columns
                    ),
                )
            )
            with cur.copy(sql.SQL("COPY {} FROM STDIN").format(raw)) as copy:
                for row in table.rows:
                    copy.write_row(row)

            kept = [c for c in table.columns if c.pii is None]
            projections: list[sql.Composable] = []
            for c in kept:
                fk = shifts.get((table.name, c.name))
                ident = sql.Identifier(c.name)
                projections.append(
                    sql.SQL("{} + {} AS {}").format(ident, sql.Literal(fk.offset), ident) if fk else ident
                )
            target = sql.Identifier(ANALYTICS, table.name)
            cur.execute(
                sql.SQL("CREATE TABLE {} AS SELECT {} FROM {}").format(target, sql.SQL(", ").join(projections), raw)
            )
            if pk := keys.primary.get(table.name):
                cur.execute(sql.SQL("ALTER TABLE {} ADD PRIMARY KEY ({})").format(target, sql.Identifier(pk)))
            withheld = [c for c in table.columns if c.pii is not None]
            cur.execute(
                sql.SQL("COMMENT ON TABLE {} IS {}").format(target, sql.Literal(describe_table(table, withheld)))
            )
            for c in kept:
                fk = shifts.get((table.name, c.name))
                shift = (fk.offset, f"{fk.parent_table}.{fk.parent_column}") if fk else None
                cur.execute(
                    sql.SQL("COMMENT ON COLUMN {} IS {}").format(
                        sql.Identifier(ANALYTICS, table.name, c.name),
                        sql.Literal(describe_column(c, len(table.rows), shift)),
                    )
                )

        for fk in keys.foreign:
            cur.execute(
                sql.SQL("ALTER TABLE {} ADD FOREIGN KEY ({}) REFERENCES {} ({})").format(
                    sql.Identifier(ANALYTICS, fk.table),
                    sql.Identifier(fk.column),
                    sql.Identifier(ANALYTICS, fk.parent_table),
                    sql.Identifier(fk.parent_column),
                )
            )

        _ensure_reader(cur, reader_url, statement_timeout_ms)
