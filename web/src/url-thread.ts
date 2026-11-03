import { useCallback, useEffect, useState } from "react";

const PARAM = "thread";

function read(): string | null {
  return new URLSearchParams(window.location.search).get(PARAM);
}

/** The active thread id, mirrored in `?thread=` so a reload or shared link restores it. */
export function useUrlThread() {
  const [threadId, setThreadId] = useState<string | null>(read);

  useEffect(() => {
    const onPop = () => {
      setThreadId(read());
    };
    window.addEventListener("popstate", onPop);
    return () => {
      window.removeEventListener("popstate", onPop);
    };
  }, []);

  const select = useCallback((id: string | null, mode: "push" | "replace" = "push") => {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set(PARAM, id);
    else url.searchParams.delete(PARAM);
    if (url.href !== window.location.href) {
      if (mode === "push") window.history.pushState(null, "", url);
      else window.history.replaceState(null, "", url);
    }
    setThreadId(id);
  }, []);

  return [threadId, select] as const;
}
