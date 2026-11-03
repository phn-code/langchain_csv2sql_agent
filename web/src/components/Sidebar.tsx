import { useMemo, useState } from "react";
import type { ThreadSummary } from "../conversation";
import type { Datasets } from "../datasets";
import { relativeTime } from "../format";
import { buildExplorer } from "../schema-model";
import { Dropzone, UploadStatus } from "./Upload";
import { LinkIcon, PlusIcon, ReportIcon } from "./icons";
import { SchemaExplorer } from "./SchemaExplorer";

type Pane = "data" | "threads";

function DataPane({ datasets, onFiles }: { datasets: Datasets; onFiles: (files: File[]) => void }) {
  const { schema, report, upload } = datasets;
  const tables = useMemo(
    () => (schema.kind === "ready" ? buildExplorer(schema.schema, report) : []),
    [schema, report],
  );
  const relationships = tables.flatMap((t) =>
    t.columns.flatMap((c) => (c.target ? [{ from: t.name, column: c.name, to: c.target }] : [])),
  );
  const busy = upload.kind === "uploading" || upload.kind === "processing";

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Dropzone onFiles={onFiles} busy={busy} />
        <UploadStatus state={upload} onDismiss={datasets.dismissError} />
      </div>

      {schema.kind === "loading" && (
        <div className="space-y-2" aria-label="Loading schema">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-11 animate-pulse rounded-lg bg-surface-2" />
          ))}
        </div>
      )}
      {schema.kind === "error" && (
        <div role="alert" className="rounded-lg bg-danger-soft p-3 text-[12.5px] text-danger">
          <p>{schema.message}</p>
          <button type="button" onClick={() => void datasets.refresh()} className="mt-1 font-semibold underline">
            Retry
          </button>
        </div>
      )}
      {schema.kind === "ready" && tables.length === 0 && (
        <p className="px-1 text-[12.5px] text-muted">No tables yet. Upload a CSV to get started.</p>
      )}
      {tables.length > 0 && (
        <section aria-labelledby="tables-heading">
          <div className="mb-1 flex items-center justify-between px-1">
            <h2 id="tables-heading" className="text-[11px] font-semibold uppercase tracking-wider text-muted">
              Tables <span className="font-normal">({tables.length})</span>
            </h2>
            {report && (
              <button
                type="button"
                onClick={() => {
                  datasets.showReport(report);
                }}
                className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[11.5px] font-medium text-accent hover:bg-accent-soft"
              >
                <ReportIcon className="size-3.5" /> Ingest report
              </button>
            )}
          </div>
          <SchemaExplorer tables={tables} onDelete={datasets.removeTable} />
        </section>
      )}
      {relationships.length > 0 && (
        <section aria-labelledby="rels-heading">
          <h2 id="rels-heading" className="mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-wider text-muted">
            Relationships <span className="font-normal">({relationships.length})</span>
          </h2>
          <ul className="space-y-1 rounded-lg border border-line bg-surface p-2">
            {relationships.map((r) => (
              <li key={`${r.from}.${r.column}`} className="font-mono text-[11px] leading-snug">
                <span className="block truncate">
                  <span className="text-ink">{r.from}</span>
                  <span className="text-muted">.{r.column}</span>
                </span>
                <span className="flex items-center gap-1 truncate pl-2">
                  <LinkIcon className="size-3 shrink-0 text-accent" />
                  <span className="truncate">
                    <span className="text-accent">{r.to.table}</span>
                    <span className="text-muted">.{r.to.column}</span>
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function ThreadsPane({
  threads,
  activeId,
  onSelect,
}: {
  threads: ThreadSummary[] | null;
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  if (threads === null) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-12 animate-pulse rounded-lg bg-surface-2" />
        ))}
      </div>
    );
  }
  if (threads.length === 0) return <p className="px-1 text-[12.5px] text-muted">No past analyses yet.</p>;
  return (
    <ul className="space-y-0.5">
      {threads.map((t) => (
        <li key={t.id}>
          <button
            type="button"
            onClick={() => {
              onSelect(t.id);
            }}
            aria-current={t.id === activeId ? "page" : undefined}
            className={`w-full rounded-lg px-2.5 py-2 text-left hover:bg-surface-2 ${
              t.id === activeId ? "bg-surface shadow-[inset_2px_0_0_var(--accent)]" : ""
            }`}
          >
            <span className="line-clamp-2 text-[13px] leading-snug text-ink">{t.title}</span>
            <span className="text-[11px] text-muted">{relativeTime(t.updatedAt)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function Sidebar({
  datasets,
  threads,
  activeThreadId,
  onSelectThread,
  onNewThread,
  onFiles,
}: {
  datasets: Datasets;
  threads: ThreadSummary[] | null;
  activeThreadId: string | null;
  onSelectThread: (id: string) => void;
  onNewThread: () => void;
  onFiles: (files: File[]) => void;
}) {
  const [pane, setPane] = useState<Pane>("data");
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-3 pb-3 pt-1">
        <div role="tablist" aria-label="Sidebar" className="flex flex-1 rounded-lg bg-surface-2 p-0.5">
          {(["data", "threads"] as const).map((p) => (
            <button
              key={p}
              role="tab"
              type="button"
              aria-selected={pane === p}
              onClick={() => {
                setPane(p);
              }}
              className={`flex-1 rounded-md px-2 py-1 text-[12.5px] font-medium ${
                pane === p ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
              }`}
            >
              {p === "data" ? "Data" : "History"}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onNewThread}
          className="inline-flex items-center gap-1 rounded-lg border border-line bg-surface px-2 py-1.5 text-[12.5px] font-medium text-ink hover:border-line-strong"
          aria-label="New analysis"
          title="New analysis"
        >
          <PlusIcon className="size-3.5" strokeWidth={2.2} />
          New
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        {pane === "data" ? (
          <DataPane datasets={datasets} onFiles={onFiles} />
        ) : (
          <ThreadsPane threads={threads} activeId={activeThreadId} onSelect={onSelectThread} />
        )}
      </div>
    </div>
  );
}
