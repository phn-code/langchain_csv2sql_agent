import { useEffect, useRef } from "react";
import type { Report, ReportTable } from "../contract";
import { formatCount } from "../format";
import { AlertIcon, CheckIcon, CloseIcon, KeyIcon, LinkIcon, ShieldIcon, SparkIcon, TableIcon } from "./icons";

function Stat({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2.5">
      <div className={`text-xl font-semibold tabular-nums ${tone === "warn" ? "text-warn" : "text-ink"}`}>{value}</div>
      <div className="text-[11.5px] text-muted">{label}</div>
    </div>
  );
}

function TableCard({ table }: { table: ReportTable }) {
  const skipped = table.rejected_row_count;
  return (
    <li className="rounded-lg border border-line bg-surface p-3">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <TableIcon className="size-4 self-center text-accent" />
        <span className="font-mono text-[13.5px] font-semibold text-ink">{table.name}</span>
        <span className="text-xs text-muted">
          from <span className="font-mono">{table.source}</span>
        </span>
        <span className="ml-auto text-sm font-semibold tabular-nums text-ink">{formatCount(table.rows)} rows</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 text-[11.5px]">
        {table.primary_key ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-warn-soft px-2 py-0.5 font-medium text-warn">
            <KeyIcon className="size-3" /> key <span className="font-mono">{table.primary_key}</span>
          </span>
        ) : (
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-muted">no primary key found</span>
        )}
        {skipped > 0 ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-danger-soft px-2 py-0.5 font-medium text-danger">
            <AlertIcon className="size-3" /> {formatCount(skipped)} skipped {skipped === 1 ? "row" : "rows"}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent">
            <CheckIcon className="size-3" /> every row loaded
          </span>
        )}
        {table.withheld.length > 0 && (
          <span className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 font-medium text-ink-2">
            <ShieldIcon className="size-3" /> {table.withheld.length} withheld
          </span>
        )}
      </div>
      {table.withheld.length > 0 && (
        <p className="mt-2 text-[12px] text-muted">
          <span className="font-medium text-ink-2">Withheld for privacy:</span>{" "}
          {table.withheld.map((w, i) => (
            <span key={w.column}>
              {i > 0 && ", "}
              <span className="font-mono text-ink-2">{w.column}</span> ({w.pii})
            </span>
          ))}
        </p>
      )}
      {table.rejected_rows.length > 0 && (
        <details className="mt-2 text-[12px]">
          <summary className="cursor-pointer text-muted hover:text-ink">Why rows were skipped</summary>
          <ul className="mt-1.5 max-h-40 space-y-0.5 overflow-auto rounded-md bg-surface-2 p-2 font-mono text-[11.5px]">
            {table.rejected_rows.map((r) => (
              <li key={r.line} className="flex gap-2">
                <span className="w-14 shrink-0 text-right text-muted">line {r.line}</span>
                <span className="text-ink-2">{r.reason}</span>
              </li>
            ))}
            {skipped > table.rejected_rows.length && (
              <li className="pt-1 text-muted">…and {formatCount(skipped - table.rejected_rows.length)} more</li>
            )}
          </ul>
        </details>
      )}
    </li>
  );
}

export function IngestReportBody({ report }: { report: Report }) {
  const rows = report.tables.reduce((n, t) => n + t.rows, 0);
  const skipped = report.tables.reduce((n, t) => n + t.rejected_row_count, 0);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label={report.tables.length === 1 ? "table" : "tables"} value={formatCount(report.tables.length)} />
        <Stat label="rows loaded" value={formatCount(rows)} />
        <Stat label="relationships" value={formatCount(report.relationships.length)} />
        <Stat label="rows skipped" value={formatCount(skipped)} tone={skipped > 0 ? "warn" : undefined} />
      </div>

      <section aria-labelledby="report-tables">
        <h3 id="report-tables" className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
          Tables
        </h3>
        <ul className="space-y-2">
          {report.tables.map((t) => (
            <TableCard key={t.name} table={t} />
          ))}
        </ul>
      </section>

      <section aria-labelledby="report-rels">
        <h3 id="report-rels" className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
          Relationships found
        </h3>
        {report.relationships.length === 0 ? (
          <p className="text-sm text-muted">No foreign keys could be matched between these tables.</p>
        ) : (
          <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
            {report.relationships.map((r) => (
              <li key={`${r.table}.${r.column}`} className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2">
                <span className="font-mono text-[12.5px] text-ink">
                  {r.table}.<span className="font-semibold">{r.column}</span>
                </span>
                <LinkIcon className="size-3.5 text-accent" aria-label="references" />
                <span className="font-mono text-[12.5px] text-ink">
                  {r.parent_table}.<span className="font-semibold">{r.parent_column}</span>
                </span>
                <span className="ml-auto flex flex-wrap gap-1.5">
                  {r.offset !== 0 && (
                    <span className="rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-medium text-warn">
                      IDs shifted by {r.offset > 0 ? "+" : ""}
                      {r.offset} to match
                    </span>
                  )}
                  {r.origin === "ai" ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent">
                      <SparkIcon className="size-3" /> AI-suggested, verified
                    </span>
                  ) : (
                    <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-muted">matched by name</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {report.rejected_relationships.length > 0 && (
        <section aria-labelledby="report-rejected">
          <h3 id="report-rejected" className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
            Considered and rejected
          </h3>
          <ul className="space-y-1.5">
            {report.rejected_relationships.map((r) => (
              <li
                key={`${r.table}.${r.column}->${r.parent_table}`}
                className="rounded-lg border border-dashed border-line-strong px-3 py-2 text-[12.5px]"
              >
                <span className="font-mono text-ink-2 line-through decoration-danger/60">
                  {r.table}.{r.column} → {r.parent_table}
                </span>
                <p className="mt-0.5 text-muted">{r.reason}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function IngestReportDialog({ report, onClose }: { report: Report | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (report && !dialog.open) dialog.showModal();
    if (!report && dialog.open) dialog.close();
  }, [report]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      aria-labelledby="report-title"
      className="m-auto max-h-[min(88vh,820px)] w-[min(720px,calc(100vw-24px))] overflow-hidden rounded-2xl border border-line bg-bg p-0 text-ink shadow-2xl backdrop:bg-black/40 backdrop:backdrop-blur-[2px]"
    >
      {report && (
        <div className="flex max-h-[min(88vh,820px)] flex-col">
          <header className="flex items-start gap-3 border-b border-line bg-surface px-5 py-4">
            <div>
              <h2 id="report-title" className="text-base font-semibold">
                Ingest report
              </h2>
              <p className="text-[13px] text-muted">What we inferred from your files. Ask away once it looks right.</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="ml-auto rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-ink"
              aria-label="Close report"
            >
              <CloseIcon className="size-4" />
            </button>
          </header>
          <div className="overflow-y-auto px-5 py-5">
            <IngestReportBody report={report} />
          </div>
        </div>
      )}
    </dialog>
  );
}
