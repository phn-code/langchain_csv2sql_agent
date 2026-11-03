import { useRef, useState } from "react";
import type { UploadState } from "../datasets";
import { CloseIcon, UploadIcon } from "./icons";

const ACCEPT = ".csv,.tsv,.txt,text/csv,text/tab-separated-values,text/plain";
export function UploadStatus({ state, onDismiss }: { state: UploadState; onDismiss: () => void }) {
  switch (state.kind) {
    case "idle":
      return null;
    case "uploading":
    case "processing": {
      const pct = state.kind === "uploading" ? Math.round(state.fraction * 100) : null;
      return (
        <div className="rounded-lg border border-line bg-surface p-2.5" role="status" aria-live="polite">
          <div className="flex items-baseline justify-between gap-2 text-[12px]">
            <span className="truncate font-medium text-ink">{state.files.join(", ")}</span>
            <span className="shrink-0 tabular-nums text-muted">{pct === null ? "Inferring schema…" : `${pct}%`}</span>
          </div>
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-2">
            <div
              className={`h-full rounded-full bg-accent transition-[width] ${pct === null ? "w-1/3 animate-[indeterminate_1.1s_ease-in-out_infinite]" : ""}`}
              style={pct === null ? undefined : { width: `${pct}%` }}
            />
          </div>
        </div>
      );
    }
    case "error":
      return (
        <div role="alert" className="flex items-start gap-2 rounded-lg bg-danger-soft p-2.5 text-[12px] text-danger">
          <span className="flex-1">{state.message}</span>
          <button type="button" onClick={onDismiss} aria-label="Dismiss error" className="rounded p-0.5 hover:bg-danger/10">
            <CloseIcon className="size-3.5" />
          </button>
        </div>
      );
  }
}

export function Dropzone({ onFiles, busy }: { onFiles: (files: File[]) => void; busy: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => {
        setOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setOver(false);
        onFiles([...e.dataTransfer.files]);
      }}
      className={`flex items-center gap-2 rounded-lg border border-dashed px-2.5 py-2 transition-colors ${
        over ? "border-accent bg-accent-soft" : "border-line-strong"
      }`}
    >
      <span className="min-w-0 flex-1 text-[11.5px] leading-snug text-muted">Drop CSV, TSV or TXT files</span>
      <button
        type="button"
        disabled={busy}
        onClick={() => input.current?.click()}
        className="inline-flex shrink-0 items-center gap-1 rounded-md bg-accent px-2 py-1 text-[12px] font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50"
      >
        <UploadIcon className="size-3.5" strokeWidth={2.2} />
        Upload
      </button>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple
        className="hidden"
        aria-label="Upload CSV files"
        onChange={(e) => {
          onFiles([...(e.target.files ?? [])]);
          e.target.value = "";
        }}
      />
    </div>
  );
}

