import { useEffect, useRef, useState } from "react";
import type { ChatSession, ThreadSummary } from "../conversation";
import type { Datasets } from "../datasets";
import { useTheme } from "../theme";
import { useWindowDrop } from "../window-drop";
import { Composer } from "./Composer";
import { Conversation } from "./Conversation";
import { EmptyState } from "./EmptyState";
import { CloseIcon, MenuIcon, MonitorIcon, MoonIcon, SunIcon, UploadIcon } from "./icons";
import { IngestReportDialog } from "./IngestReport";
import { Sidebar } from "./Sidebar";

const THEME_ICON = { system: MonitorIcon, light: SunIcon, dark: MoonIcon };

function Brand() {
  return (
    <div className="flex items-center gap-2">
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden="true">
        <rect width="32" height="32" rx="8" fill="var(--accent)" />
        <path d="M8 10h16M8 16h16M8 22h10" stroke="var(--accent-ink)" strokeWidth="2.5" strokeLinecap="round" />
        <circle cx="23" cy="22" r="2.5" fill="#fbbf24" />
      </svg>
      <span className="text-[15px] font-semibold tracking-tight text-ink">
        csv<span className="text-accent">2</span>sql
      </span>
    </div>
  );
}

export function Workspace({
  session,
  datasets,
  threads,
  threadId,
  onSelectThread,
  onNewThread,
}: {
  session: ChatSession;
  datasets: Datasets;
  threads: ThreadSummary[] | null;
  threadId: string | null;
  onSelectThread: (id: string) => void;
  onNewThread: () => void;
}) {
  const theme = useTheme();
  const [drawer, setDrawer] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const dragging = useWindowDrop((files) => void datasets.uploadFiles(files));
  const ThemeIcon = THEME_ICON[theme.preference];

  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawer(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [drawer]);

  const tables = datasets.schema.kind === "ready" ? datasets.schema.schema.tables.map((t) => t.name) : null;
  const closeDrawer = (fn: () => void) => () => {
    fn();
    setDrawer(false);
  };

  return (
    <div className="flex h-full bg-bg">
      <aside
        aria-label="Data and history"
        className={`fixed inset-y-0 left-0 z-40 flex w-[min(320px,88vw)] flex-col border-r border-line bg-bg pt-3 transition-transform lg:static lg:z-auto lg:w-[300px] lg:translate-x-0 ${
          drawer ? "translate-x-0 shadow-2xl" : "-translate-x-full max-lg:invisible"
        }`}
      >
        <div className="flex items-center justify-between px-4 pb-3">
          <Brand />
          <button
            type="button"
            className="rounded-md p-1.5 text-muted hover:bg-surface-2 lg:hidden"
            onClick={() => {
              setDrawer(false);
            }}
            aria-label="Close sidebar"
          >
            <CloseIcon className="size-4" />
          </button>
        </div>
        <Sidebar
          datasets={datasets}
          threads={threads}
          activeThreadId={threadId}
          onSelectThread={(id) => {
            onSelectThread(id);
            setDrawer(false);
          }}
          onNewThread={closeDrawer(onNewThread)}
          onFiles={(files) => void datasets.uploadFiles(files)}
        />
      </aside>
      {drawer && (
        <div
          className="fixed inset-0 z-30 bg-black/30 lg:hidden"
          onClick={() => {
            setDrawer(false);
          }}
          aria-hidden="true"
        />
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b border-line px-3 py-2 sm:px-4">
          <button
            type="button"
            className="rounded-md p-1.5 text-ink-2 hover:bg-surface-2 lg:hidden"
            onClick={() => {
              setDrawer(true);
            }}
            aria-label="Open sidebar"
          >
            <MenuIcon className="size-5" />
          </button>
          <div className="lg:hidden">
            <Brand />
          </div>
          <p className="hidden truncate text-sm text-muted lg:block">
            {session.turns[0]?.question ?? "New analysis"}
          </p>
          <button
            type="button"
            onClick={theme.cycle}
            className="ml-auto inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[12.5px] text-ink-2 hover:bg-surface-2"
            aria-label={`Theme: ${theme.preference}. Switch theme`}
            title={`Theme: ${theme.preference}`}
          >
            <ThemeIcon className="size-4" />
            <span className="hidden capitalize sm:inline">{theme.preference}</span>
          </button>
        </header>

        <div data-scroller className="min-h-0 flex-1 overflow-y-auto">
          {session.turns.length === 0 ? (
            <EmptyState
              tables={tables}
              upload={datasets.upload}
              onAsk={session.submit}
              onLoadSample={() => void datasets.loadSample()}
              onBrowse={() => fileInput.current?.click()}
            />
          ) : (
            <Conversation session={session} theme={theme.resolved} />
          )}
        </div>

        <div className="mx-auto w-full max-w-3xl px-3 pb-3 pt-1 sm:px-6 sm:pb-5">
          <Composer streaming={session.isStreaming} onSubmit={session.submit} onStop={session.stop} />
          <p className="mt-1.5 hidden text-center text-[11px] text-muted sm:block">
            Enter to send, Shift+Enter for a new line. Answers come from SQL over your tables; check the query.
          </p>
        </div>
      </main>

      <input
        ref={fileInput}
        type="file"
        accept=".csv,.tsv,.txt"
        multiple
        className="hidden"
        aria-hidden="true"
        tabIndex={-1}
        onChange={(e) => {
          void datasets.uploadFiles([...(e.target.files ?? [])]);
          e.target.value = "";
        }}
      />

      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-50 grid place-items-center bg-accent/10 p-6 backdrop-blur-[1px]">
          <div className="flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-accent bg-surface px-10 py-8 text-center shadow-xl">
            <UploadIcon className="size-8 text-accent" />
            <p className="text-base font-semibold text-ink">Drop to load into SQL</p>
            <p className="text-sm text-muted">CSV, TSV or TXT, up to 50 MB each</p>
          </div>
        </div>
      )}

      <IngestReportDialog
        report={datasets.shownReport}
        onClose={() => {
          datasets.showReport(null);
        }}
      />
    </div>
  );
}
