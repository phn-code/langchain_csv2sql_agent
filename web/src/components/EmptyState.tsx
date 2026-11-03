import type { UploadState } from "../datasets";
import { ChartIcon, SparkIcon, TableIcon, UploadIcon } from "./icons";

const BAKERY_EXAMPLES = [
  "Which product earned the most revenue?",
  "Plot daily revenue over time",
  "Revenue by country as a bar chart",
  "Which franchises have the most reviews, and who supplies them?",
];

function exampleQuestions(tables: string[]): string[] {
  if (tables.includes("sales_transactions")) return BAKERY_EXAMPLES;
  const [a, b] = tables;
  if (!a) return [];
  return [`How many rows are in ${a}?`, `Describe the ${a} table`, `How many rows are in ${b ?? a}?`].filter(
    (q, i, all) => all.indexOf(q) === i,
  );
}

export function EmptyState({
  tables,
  upload,
  onAsk,
  onLoadSample,
  onBrowse,
}: {
  tables: string[] | null;
  upload: UploadState;
  onAsk: (q: string) => void;
  onLoadSample: () => void;
  onBrowse: () => void;
}) {
  if (tables === null) return null;
  if (tables.length === 0) {
    const busy = upload.kind === "uploading" || upload.kind === "processing";
    return (
      <div className="mx-auto flex max-w-lg flex-col items-center px-4 py-12 text-center sm:py-20">
        <div className="grid size-14 place-items-center rounded-2xl bg-accent-soft text-accent">
          <UploadIcon className="size-7" />
        </div>
        <h1 className="mt-5 text-2xl font-semibold tracking-tight text-ink">Bring a CSV, ask it anything</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">
          Drop one or more CSV files anywhere on this page. We infer types, keys and relationships, hold back personal
          data, and load it into SQL so you can ask questions in plain English.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            type="button"
            onClick={onBrowse}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50"
          >
            <UploadIcon className="size-4" strokeWidth={2.2} /> Upload CSV files
          </button>
          <button
            type="button"
            onClick={onLoadSample}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-4 py-2 text-sm font-medium text-ink hover:border-line-strong disabled:opacity-50"
          >
            Load the bakery sample
          </button>
        </div>
        <p className="mt-3 text-xs text-muted">The sample is six tables from a fictional bakery franchise.</p>
      </div>
    );
  }
  const examples = exampleQuestions(tables);
  const icons = [TableIcon, ChartIcon, ChartIcon, SparkIcon];
  return (
    <div className="mx-auto max-w-2xl px-4 py-10 sm:py-16">
      <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">What do you want to know?</h1>
      <p className="mt-2 text-[15px] text-muted">
        Ask in plain English. Every answer shows the SQL it ran, the rows it got back, and a chart when one helps.
      </p>
      <ul className="mt-6 grid gap-2 sm:grid-cols-2">
        {examples.map((q, i) => {
          const Icon = icons[i] ?? SparkIcon;
          return (
            <li key={q}>
              <button
                type="button"
                onClick={() => {
                  onAsk(q);
                }}
                className="group flex h-full w-full items-start gap-3 rounded-xl border border-line bg-surface p-3.5 text-left transition hover:-translate-y-px hover:border-accent/50 hover:shadow-sm"
              >
                <Icon className="mt-0.5 size-4 shrink-0 text-muted group-hover:text-accent" />
                <span className="text-sm leading-snug text-ink">{q}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
