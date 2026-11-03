import { stepNames, type StepName } from "../contract";
import { MAX_ATTEMPTS, type RunProgress as Progress, type StepStatus } from "../conversation";
import { AlertIcon, CheckIcon, RetryIcon } from "./icons";

const LABELS: Record<StepName, string> = {
  plan: "Understanding",
  write_sql: "Writing SQL",
  run_sql: "Running",
  respond: "Answering",
};

function Dot({ status }: { status: StepStatus }) {
  switch (status) {
    case "done":
      return (
        <span className="grid size-5 place-items-center rounded-full bg-accent text-accent-ink">
          <CheckIcon className="size-3" strokeWidth={3} />
        </span>
      );
    case "active":
      return (
        <span className="pulse-ring grid size-5 place-items-center rounded-full border-2 border-accent bg-surface">
          <span className="size-1.5 rounded-full bg-accent" />
        </span>
      );
    case "failed":
      return (
        <span className="grid size-5 place-items-center rounded-full bg-danger text-white">
          <span className="text-[11px] font-bold leading-none">!</span>
        </span>
      );
    case "pending":
      return <span className="size-5 rounded-full border-2 border-line-strong bg-surface" />;
  }
}

export function RunProgress({ progress }: { progress: Progress }) {
  const attempt = progress.failures.length + 1;
  const active = stepNames.find((s) => progress.steps[s] === "active");
  return (
    <div className="rounded-xl border border-line bg-surface p-4" role="status" aria-live="polite">
      <span className="sr-only">{active ? `${LABELS[active]}…` : "Working…"}</span>
      <ol className="flex items-start">
        {stepNames.map((step, i) => {
          const status = progress.steps[step];
          return (
            <li key={step} className="flex flex-1 items-start last:flex-none">
              <div className="flex flex-col items-center gap-1.5">
                <Dot status={status} />
                <span
                  className={`whitespace-nowrap text-[11px] font-medium sm:text-xs ${
                    status === "pending" ? "text-muted" : status === "failed" ? "text-danger" : "text-ink"
                  }`}
                >
                  {LABELS[step]}
                </span>
                {step === "write_sql" && progress.failures.length > 0 && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-warn-soft px-1.5 py-0.5 text-[10px] font-semibold text-warn">
                    <RetryIcon className="size-3" />
                    {Math.min(attempt, MAX_ATTEMPTS)}/{MAX_ATTEMPTS}
                  </span>
                )}
              </div>
              {i < stepNames.length - 1 && (
                <div
                  className={`mx-1.5 mt-2.5 h-0.5 flex-1 rounded-full sm:mx-3 ${status === "done" ? "bg-accent" : "bg-line"}`}
                />
              )}
            </li>
          );
        })}
      </ol>
      {progress.failures.length > 0 && (
        <ul className="mt-4 space-y-1.5 border-t border-line pt-3">
          {progress.failures.map((error, i) => (
            <li key={i} className="flex items-start gap-2 text-xs text-ink-2">
              <AlertIcon className="mt-px size-3.5 shrink-0 text-warn" />
              <span>
                <span className="font-semibold text-warn">Attempt {i + 1} failed.</span>{" "}
                <span className="font-mono text-[11.5px]">{error}</span>
                {i === progress.failures.length - 1 && progress.steps.write_sql === "active" && (
                  <span className="mt-0.5 block text-muted">Rewriting the query…</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
