"""`csv2sql-ingest DIR`: load every CSV in DIR into Postgres and print what was inferred."""

import argparse
import sys
from pathlib import Path

import psycopg

from csv2sql.ingest.keys import Keys, infer_keys
from csv2sql.ingest.load import load
from csv2sql.ingest.profile import Table, read_table
from csv2sql.settings import Settings


def report(tables: list[Table], keys: Keys) -> str:
    lines: list[str] = []
    for table in tables:
        pk = keys.primary.get(table.name)
        lines.append(f"{table.name}  {len(table.rows):,} rows  primary key: {pk or 'none found'}")
        lines.extend(f"  skipped line {r.line}: {r.reason}" for r in table.rejected)
        lines.extend(f"  withheld {c.name} ({c.pii})" for c in table.columns if c.pii)
    lines.append("relationships")
    for fk in keys.foreign:
        shift = f"  (shifted {fk.offset:+,})" if fk.offset else ""
        lines.append(f"  {fk.table}.{fk.column} -> {fk.parent_table}.{fk.parent_column}{shift}")
    lines.extend(f"  rejected {r.table}.{r.column} -> {r.parent_table}: {r.reason}" for r in keys.rejected)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Infer and report without touching the database.")
    args = parser.parse_args()

    paths = sorted(args.directory.glob("*.csv"))
    if not paths:
        sys.exit(f"No CSV files in {args.directory}")
    tables = [read_table(p) for p in paths]
    keys = infer_keys(tables)
    print(report(tables, keys))
    if args.dry_run:
        return

    settings = Settings()  # type: ignore[call-arg]
    if settings.database_url is None:
        sys.exit("DATABASE_URL is required to load data")
    with psycopg.connect(str(settings.database_url)) as conn:
        load(conn, tables, keys, str(settings.reader_database_url), settings.statement_timeout_ms)
    print(f"Loaded {len(tables)} tables")


if __name__ == "__main__":
    main()
