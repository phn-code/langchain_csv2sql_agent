import { useRef, useState } from "react";
import { formatCount } from "../format";
import { columnNote, type ExplorerColumn, type ExplorerTable } from "../schema-model";
import { ChevronIcon, KeyIcon, LinkIcon, ShieldIcon, SparkIcon, TrashIcon } from "./icons";

function TypeLabel({ type }: { type: string }) {
  return <span className="shrink-0 font-mono text-[10.5px] uppercase tracking-wide text-muted">{type}</span>;
}

function ColumnRow({ column, onJump }: { column: ExplorerColumn; onJump: (table: string) => void }) {
  const { origin, note } = columnNote(column.comment);
  return (
    <li className="py-1.5 pl-3 pr-2">
      <div className="flex items-center gap-1.5">
        <span className="truncate font-mono text-[12.5px] text-ink" title={column.name}>
          {column.name}
        </span>
        {column.primary_key && (
          <span
            className="inline-flex items-center gap-0.5 rounded bg-warn-soft px-1 py-px text-[10px] font-bold text-warn"
            title="Primary key"
          >
            <KeyIcon className="size-2.5" strokeWidth={2.4} />
            PK
          </span>
        )}
        {column.target && (
          <span className="rounded bg-accent-soft px-1 py-px text-[10px] font-bold text-accent" title="Foreign key">
            FK
          </span>
        )}
        <span className="ml-auto" />
        <TypeLabel type={column.type} />
      </div>
      {column.target && (
        <button
          type="button"
          onClick={() => {
            if (column.target) onJump(column.target.table);
          }}
          className="mt-0.5 inline-flex max-w-full items-center gap-1 rounded text-[11.5px] text-accent hover:underline"
          aria-label={`Jump to ${column.target.table}`}
        >
          <LinkIcon className="size-3 shrink-0" />
          <span className="truncate">
            {column.target.table}.{column.target.column}
          </span>
        </button>
      )}
      {column.link && (column.link.origin === "ai" || column.link.offset !== 0) && (
        <div className="mt-0.5 flex flex-wrap gap-1">
          {column.link.origin === "ai" && (
            <span className="inline-flex items-center gap-0.5 text-[10.5px] text-muted">
              <SparkIcon className="size-2.5" /> AI-suggested, verified
            </span>
          )}
          {column.link.offset !== 0 && (
            <span className="text-[10.5px] text-muted">
              IDs shifted by {column.link.offset > 0 ? "+" : ""}
              {column.link.offset}
            </span>
          )}
        </div>
      )}
      {note && <p className="mt-0.5 text-[11.5px] leading-snug text-muted">{note}</p>}
      {origin && origin !== column.name && (
        <p className="mt-0.5 text-[10.5px] text-muted/80">
          CSV: <span className="font-mono">{origin}</span>
        </p>
      )}
    </li>
  );
}

function DeleteTable({ table, onDelete }: { table: string; onDelete: (table: string) => Promise<void> }) {
  const [state, setState] = useState<"idle" | "confirm" | "deleting">("idle");
  if (state === "idle") {
    return (
      <button
        type="button"
        onClick={() => {
          setState("confirm");
        }}
        className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px] text-muted hover:bg-danger-soft hover:text-danger"
        aria-label={`Delete table ${table}`}
      >
        <TrashIcon className="size-3.5" /> Delete
      </button>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[11.5px]" role="group" aria-label={`Confirm deleting ${table}`}>
      <span className="text-danger">Delete {table}?</span>
      <button
        type="button"
        disabled={state === "deleting"}
        onClick={() => {
          setState("deleting");
          void onDelete(table).finally(() => {
            setState("idle");
          });
        }}
        className="rounded bg-danger px-1.5 py-0.5 font-semibold text-white disabled:opacity-60"
      >
        {state === "deleting" ? "Deleting…" : "Delete"}
      </button>
      <button
        type="button"
        onClick={() => {
          setState("idle");
        }}
        className="rounded px-1.5 py-0.5 text-ink-2 hover:bg-surface-2"
      >
        Cancel
      </button>
    </span>
  );
}

export function SchemaExplorer({
  tables,
  onDelete,
}: {
  tables: ExplorerTable[];
  onDelete: (table: string) => Promise<void>;
}) {
  const [open, setOpen] = useState<ReadonlySet<string>>(() => new Set());
  const [flash, setFlash] = useState<string | null>(null);
  const refs = useRef(new Map<string, HTMLElement>());

  const toggle = (name: string) => {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const jump = (name: string) => {
    setOpen((prev) => new Set(prev).add(name));
    setFlash(name);
    setTimeout(() => {
      setFlash((f) => (f === name ? null : f));
    }, 1200);
    requestAnimationFrame(() => {
      const el = refs.current.get(name);
      el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      el?.querySelector("button")?.focus({ preventScroll: true });
    });
  };

  return (
    <ul className="space-y-1.5">
      {tables.map((t) => {
        const expanded = open.has(t.name);
        const panelId = `table-${t.name}`;
        return (
          <li
            key={t.name}
            ref={(el) => {
              if (el) refs.current.set(t.name, el);
              else refs.current.delete(t.name);
            }}
            className={`rounded-lg border transition-colors duration-500 ${
              flash === t.name ? "border-accent bg-accent-soft" : expanded ? "border-line bg-surface" : "border-transparent"
            }`}
          >
            <button
              type="button"
              aria-expanded={expanded}
              aria-controls={panelId}
              onClick={() => {
                toggle(t.name);
              }}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left hover:bg-surface-2"
            >
              <ChevronIcon className={`size-3.5 shrink-0 text-muted transition-transform ${expanded ? "rotate-90" : ""}`} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-mono text-[13px] font-medium text-ink">{t.name}</span>
                <span className="block truncate text-[11.5px] text-muted">
                  {t.rows !== null ? `${formatCount(t.rows)} rows` : "rows unknown"} · {t.columns.length} columns
                  {t.withheld.length > 0 && ` · ${t.withheld.length} withheld`}
                </span>
              </span>
            </button>
            {expanded && (
              <div id={panelId} className="pb-2">
                {(t.source || t.note) && (
                  <p className="px-3 pb-1 text-[11.5px] text-muted">
                    {t.source && (
                      <>
                        From <span className="font-mono text-ink-2">{t.source}</span>.{" "}
                      </>
                    )}
                    {t.note}
                  </p>
                )}
                <ul className="divide-y divide-line/60">
                  {t.columns.map((c) => (
                    <ColumnRow key={c.name} column={c} onJump={jump} />
                  ))}
                </ul>
                {t.withheld.length > 0 && (
                  <div className="mx-2 mt-2 rounded-md border border-dashed border-line-strong px-2.5 py-2">
                    <p className="flex items-center gap-1.5 text-[11.5px] font-semibold text-ink-2">
                      <ShieldIcon className="size-3.5 text-accent" /> Withheld for privacy
                    </p>
                    <ul className="mt-1 space-y-0.5">
                      {t.withheld.map((w) => (
                        <li key={w.column} className="flex items-baseline justify-between gap-2 text-[11.5px]">
                          <span className="font-mono text-muted line-through decoration-line-strong">{w.column}</span>
                          <span className="text-muted">{w.pii}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {t.referencedBy.length > 0 && (
                  <div className="px-3 pt-2 text-[11.5px] text-muted">
                    Referenced by{" "}
                    {t.referencedBy.map((r, i) => (
                      <span key={`${r.table}.${r.via}`}>
                        {i > 0 && ", "}
                        <button
                          type="button"
                          onClick={() => {
                            jump(r.table);
                          }}
                          className="font-mono text-accent hover:underline"
                        >
                          {r.table}.{r.via}
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex justify-end px-2 pt-1.5">
                  <DeleteTable table={t.name} onDelete={onDelete} />
                </div>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
