"""`csv2sql-ingest DIR`: load every CSV in DIR into Postgres and print what was inferred."""

import argparse
import json
import sys
from pathlib import Path

import psycopg

from csv2sql.ingest.pipeline import Report, enrichment_model, ingest
from csv2sql.settings import Settings


def summarize(report: Report) -> str:
    lines: list[str] = []
    for t in report["tables"]:
        lines.append(f"{t['name']}  {t['rows']:,} rows  primary key: {t['primary_key'] or 'none found'}")
        lines.extend(f"  skipped line {r['line']}: {r['reason']}" for r in t["rejected_rows"])
        lines.extend(f"  withheld {w['column']} ({w['pii']})" for w in t["withheld"])
    lines.append("relationships")
    for f in report["relationships"]:
        notes = [f"shifted {f['offset']:+,}"] if f["offset"] else []
        notes += ["suggested by AI"] if f["origin"] == "ai" else []
        suffix = f"  ({', '.join(notes)})" if notes else ""
        lines.append(f"  {f['table']}.{f['column']} -> {f['parent_table']}.{f['parent_column']}{suffix}")
    lines.extend(
        f"  rejected {r['table']}.{r['column']} -> {r['parent_table']}: {r['reason']}"
        for r in report["rejected_relationships"]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Infer and report without touching the database.")
    parser.add_argument("--no-ai", action="store_true", help="Skip AI descriptions and relationship suggestions.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = parser.parse_args()

    settings = Settings()  # type: ignore[call-arg]
    model = None if args.no_ai else enrichment_model(settings)
    if args.dry_run:
        report = ingest(args.directory, None, reader_url="", statement_timeout_ms=0, model=model)
    else:
        if settings.database_url is None:
            sys.exit("DATABASE_URL is required to load data")
        with psycopg.connect(str(settings.database_url)) as conn:
            report = ingest(
                args.directory,
                conn,
                reader_url=str(settings.reader_database_url),
                statement_timeout_ms=settings.statement_timeout_ms,
                model=model,
            )
    print(json.dumps(report, indent=2) if args.json else summarize(report))


if __name__ == "__main__":
    main()
