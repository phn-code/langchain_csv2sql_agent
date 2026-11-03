import { Client, type Message } from "@langchain/langgraph-sdk";
import { useStream } from "@langchain/langgraph-sdk/react";
import { useCallback, useMemo, useState } from "react";
import { config } from "./config";
import { parseProgressEvent } from "./contract";
import {
  initialProgress,
  messageText,
  reduceProgress,
  toTurns,
  type ChatSession,
  type RunProgress,
  type ThreadSummary,
} from "./conversation";

export const client = new Client({ apiUrl: config.apiUrl });

type State = { messages: Message[] };

export function useLiveSession(threadId: string | null, onThreadId: (id: string) => void): ChatSession {
  const [progress, setProgress] = useState<RunProgress | null>(null);
  const stream = useStream<State>({
    client,
    assistantId: config.assistantId,
    threadId,
    onThreadId,
    messagesKey: "messages",
    reconnectOnMount: true,
    onCustomEvent: (data) => {
      const event = parseProgressEvent(data);
      if (event) setProgress((prev) => reduceProgress(prev ?? initialProgress, event));
    },
  });

  const { submit: streamSubmit, stop: streamStop } = stream;
  const submit = useCallback(
    (question: string) => {
      setProgress(initialProgress);
      void streamSubmit(
        { messages: [{ type: "human", content: question }] },
        {
          streamMode: ["values", "messages-tuple", "custom"],
          optimisticValues: (prev) => ({
            messages: [...(prev.messages ?? []), { type: "human", content: question, id: `pending-${Date.now()}` }],
          }),
        },
      );
    },
    [streamSubmit],
  );
  const stop = useCallback(() => void streamStop(), [streamStop]);

  const turns = useMemo(() => toTurns(stream.messages), [stream.messages]);
  const error = stream.error ? describeError(stream.error) : null;
  return { turns, isStreaming: stream.isLoading, progress: stream.isLoading ? progress : null, error, submit, stop };
}

function describeError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return typeof error === "string" ? error : "The agent run failed.";
}

export async function searchThreads(): Promise<ThreadSummary[]> {
  const threads = await client.threads.search<State>({ limit: 50, sortBy: "updated_at", sortOrder: "desc" });
  return threads.map((t) => {
    const first = Array.isArray(t.values?.messages) ? t.values.messages.find((m) => m.type === "human") : undefined;
    return { id: t.thread_id, title: first ? messageText(first) : "Untitled analysis", updatedAt: t.updated_at };
  });
}
