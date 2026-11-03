import { lazy, Suspense, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Analysis } from "../contract";
import type { Answer } from "../conversation";
import { downloadText, formatCount, rowSummary, slugify, toCsv } from "../format";
import type { ResolvedTheme } from "../theme";
import { ChartIcon, ChevronIcon, CodeIcon, DownloadIcon, RetryIcon, TableIcon } from "./icons";
import { ResultTable } from "./ResultTable";
import { CopyButton, SqlCode } from "./SqlCode";

const ChartView = lazy(() => import("./ChartView"));

type TabId = "chart" | "table" | "sql";
type Tab = { id: TabId; label: string; icon: ReactNode; panel: ReactNode };

function buildTabs(analysis: Analysis, theme: ResolvedTheme): Tab[] {
  const tabs: Tab[] = [];
  if (analysis.chart) {
    const spec = analysis.chart;
    tabs.push({
      id: "chart",
      label: "Chart",
      icon: <ChartIcon className="size-4" />,
      panel: (
        <Suspense fallback={<div className="h-[280px] animate-pulse rounded-lg bg-surface-2" />}>
          <ChartView spec={spec} theme={theme} />
        </Suspense>
      ),
    });
  }
  if (analysis.result) {
    tabs.push({
      id: "table",
      label: "Table",
      icon: <TableIcon className="size-4" />,
      panel: <ResultTable result={analysis.result} />,
    });
  }
  if (analysis.sql) {
    const sql = analysis.sql;
    tabs.push({
      id: "sql",
      label: "SQL",
      icon: <CodeIcon className="size-4" />,
      panel: (
        <div className="relative">
          <div className="absolute right-2 top-2">
            <CopyButton text={sql} label="Copy SQL" />
          </div>
          <SqlCode sql={sql} />
        </div>
      ),
    });
  }
  return tabs;
}

function ResultTabs({ analysis, theme }: { analysis: Analysis; theme: ResolvedTheme }) {
  const tabs = buildTabs(analysis, theme);
  const [selected, setSelected] = useState<TabId | null>(null);
  const baseId = useId();
  const refs = useRef(new Map<TabId, HTMLButtonElement>());
  const first = tabs[0];
  if (!first) return null;
  const current = tabs.find((t) => t.id === selected) ?? first;

  const onKeyDown = (e: KeyboardEvent) => {
    const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    const index = tabs.indexOf(current);
    const next = tabs[(index + delta + tabs.length) % tabs.length] ?? first;
    setSelected(next.id);
    refs.current.get(next.id)?.focus();
  };

  const { result } = analysis;
  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line">
        <div role="tablist" aria-label="Result views" className="-mb-px flex" onKeyDown={onKeyDown}>
          {tabs.map((tab) => {
            const active = tab.id === current.id;
            return (
              <button
                key={tab.id}
                ref={(el) => {
                  if (el) refs.current.set(tab.id, el);
                  else refs.current.delete(tab.id);
                }}
                role="tab"
                type="button"
                id={`${baseId}-tab-${tab.id}`}
                aria-selected={active}
                aria-controls={`${baseId}-panel-${tab.id}`}
                tabIndex={active ? 0 : -1}
                onClick={() => {
                  setSelected(tab.id);
                }}
                className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                  active ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"
                }`}
              >
                {tab.icon}
                {tab.label}
              </button>
            );
          })}
        </div>
        {result && (
          <div className="ml-auto flex items-center gap-3 pb-1.5 text-xs text-muted">
            <span className={result.truncated ? "font-medium text-warn" : undefined}>{rowSummary(result)}</span>
            <span aria-hidden="true">·</span>
            <span className="tabular-nums">{formatCount(result.elapsed_ms)} ms</span>
            <button
              type="button"
              onClick={() => {
                downloadText(`${slugify(analysis.question)}.csv`, toCsv(result), "text/csv");
              }}
              className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
              aria-label={`Download ${formatCount(result.rows.length)} rows as CSV`}
            >
              <DownloadIcon className="size-3.5" />
              CSV
            </button>
          </div>
        )}
      </div>
      <div
        role="tabpanel"
        id={`${baseId}-panel-${current.id}`}
        aria-labelledby={`${baseId}-tab-${current.id}`}
        className="pt-3"
      >
        {current.panel}
      </div>
      {result?.truncated && current.id === "table" && (
        <p className="mt-2 text-xs text-muted">
          Only the first {formatCount(result.rows.length)} rows came back. Ask for an aggregate or add a filter to see
          the rest.
        </p>
      )}
    </div>
  );
}

function Corrections({ failures }: { failures: Analysis["failures"] }) {
  const n = failures.length;
  return (
    <details className="group mt-4 rounded-lg border border-warn/30 bg-warn-soft/50">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-sm font-medium text-warn [&::-webkit-details-marker]:hidden">
        <RetryIcon className="size-4" />
        Self-corrected {n} {n === 1 ? "time" : "times"}
        <span className="font-normal text-muted">before the query succeeded</span>
        <ChevronIcon className="ml-auto size-4 transition-transform group-open:rotate-90" />
      </summary>
      <ol className="space-y-3 border-t border-warn/20 px-3 pb-3 pt-3">
        {failures.map((f, i) => (
          <li key={i}>
            <div className="mb-1.5 flex items-baseline gap-2 text-xs">
              <span className="font-semibold text-ink-2">Attempt {i + 1}</span>
              <span className="text-danger">{f.error}</span>
            </div>
            <SqlCode sql={f.sql} tone="failed" />
          </li>
        ))}
      </ol>
    </details>
  );
}

export function AnswerCard({
  answer,
  streaming,
  theme,
}: {
  answer: Answer;
  streaming: boolean;
  theme: ResolvedTheme;
}) {
  const { analysis } = answer;
  return (
    <article className="rounded-xl border border-line bg-surface p-4 shadow-[0_1px_2px_rgb(0_0_0/0.04)] sm:p-5">
      {answer.text && (
        <div className={`prose-answer text-[15px] text-ink-2 ${streaming ? "caret" : ""}`}>
          <Markdown remarkPlugins={[remarkGfm]}>{answer.text}</Markdown>
        </div>
      )}
      {analysis && analysis.failures.length > 0 && <Corrections failures={analysis.failures} />}
      {analysis && <ResultTabs analysis={analysis} theme={theme} />}
    </article>
  );
}
