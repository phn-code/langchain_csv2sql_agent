import type { Message } from "@langchain/langgraph-sdk";
import { parseAnalysis, type Analysis, type ProgressEvent, type StepName } from "./contract";

export type Answer = { text: string; analysis: Analysis | null };

export type Turn = {
  id: string;
  question: string;
  answer: Answer | null;
};

export type StepStatus = "pending" | "active" | "done" | "failed";

export type RunProgress = {
  steps: Record<StepName, StepStatus>;
  /** Errors from failed run_sql attempts, in order. */
  failures: string[];
};

/** What the conversation pane needs, whether backed by a live LangGraph stream or fixtures. */
export type ChatSession = {
  turns: Turn[];
  isStreaming: boolean;
  progress: RunProgress | null;
  error: string | null;
  submit: (question: string) => void;
  stop: () => void;
};

export type ThreadSummary = { id: string; title: string; updatedAt: string };

export const MAX_ATTEMPTS = 3;

export function messageText(message: Message): string {
  const { content } = message;
  if (typeof content === "string") return content;
  return content.map((part) => (part.type === "text" ? part.text : "")).join("");
}

/** Pairs each human message with the last AI message that follows it. */
export function toTurns(messages: readonly Message[]): Turn[] {
  const turns: Turn[] = [];
  for (const [index, message] of messages.entries()) {
    if (message.type === "human") {
      turns.push({ id: message.id ?? `turn-${index}`, question: messageText(message), answer: null });
      continue;
    }
    const current = turns.at(-1);
    if (message.type !== "ai" || !current) continue;
    const text = messageText(message);
    const analysis = parseAnalysis(message.additional_kwargs);
    if (text || analysis) current.answer = { text, analysis };
  }
  return turns;
}

export const initialProgress: RunProgress = {
  steps: { plan: "pending", write_sql: "pending", run_sql: "pending", respond: "pending" },
  failures: [],
};

export function reduceProgress(state: RunProgress, event: ProgressEvent): RunProgress {
  const steps = { ...state.steps };
  switch (event.status) {
    case "started":
      steps[event.step] = "active";
      // A retry restarts write_sql after run_sql failed; reset the run step for the new attempt.
      if (event.step === "write_sql") steps.run_sql = "pending";
      return { ...state, steps };
    case "done":
      steps[event.step] = "done";
      return { ...state, steps };
    case "failed":
      steps[event.step] = "failed";
      return {
        steps,
        failures: event.step === "run_sql" ? [...state.failures, event.detail ?? "Query failed"] : state.failures,
      };
    default: {
      const exhaustive: never = event.status;
      return exhaustive;
    }
  }
}
