import { useCallback, useEffect, useState } from "react";
import { Workspace } from "./components/Workspace";
import { config } from "./config";
import type { ThreadSummary } from "./conversation";
import { httpDataSource } from "./data-api";
import { useDatasets } from "./datasets";
import { searchThreads, useLiveSession } from "./live";
import { useUrlThread } from "./url-thread";

const dataSource = httpDataSource(config.dataApiUrl);

export function App() {
  const [threadId, selectThread] = useUrlThread();
  const onThreadId = useCallback((id: string) => {
    selectThread(id, "replace");
  }, [selectThread]);
  const session = useLiveSession(threadId, onThreadId);
  const datasets = useDatasets(dataSource);
  const [threads, setThreads] = useState<ThreadSummary[] | null>(null);

  // Re-list after each run so a new thread and its title show up.
  useEffect(() => {
    if (session.isStreaming) return;
    let cancelled = false;
    searchThreads()
      .then((list) => {
        if (!cancelled) setThreads(list);
      })
      .catch(() => {
        if (!cancelled) setThreads([]);
      });
    return () => {
      cancelled = true;
    };
  }, [session.isStreaming, threadId]);

  return (
    <Workspace
      session={session}
      datasets={datasets}
      threads={threads}
      threadId={threadId}
      onSelectThread={selectThread}
      onNewThread={() => {
        selectThread(null);
      }}
    />
  );
}
