import { useEffect, useRef } from "react";
import type { ChatSession } from "../conversation";
import type { ResolvedTheme } from "../theme";
import { AnswerCard } from "./AnswerCard";
import { AlertIcon } from "./icons";
import { RunProgress } from "./RunProgress";

export function Conversation({ session, theme }: { session: ChatSession; theme: ResolvedTheme }) {
  const { turns, isStreaming, progress, error } = session;
  const end = useRef<HTMLDivElement>(null);
  const last = turns.at(-1);

  // Follow the stream only while the reader is already near the bottom.
  useEffect(() => {
    const el = end.current;
    const scroller = el?.closest("[data-scroller]");
    if (!el || !scroller) return;
    const distance = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    if (distance < 240) el.scrollIntoView({ block: "end" });
  }, [turns, progress]);

  return (
    <div className="mx-auto w-full max-w-3xl space-y-8 px-4 py-6 sm:px-6 sm:py-8">
      {turns.map((turn) => {
        const isLast = turn === last;
        const live = isLast && isStreaming;
        return (
          <section key={turn.id} aria-label={`Question: ${turn.question}`} className="space-y-3">
            <div className="flex justify-end">
              <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-[15px] leading-relaxed text-bg">
                {turn.question}
              </p>
            </div>
            {live && progress && <RunProgress progress={progress} />}
            {turn.answer && <AnswerCard answer={turn.answer} streaming={live} theme={theme} />}
            {live && !progress && !turn.answer && (
              <div className="h-16 animate-pulse rounded-xl bg-surface-2" aria-label="Waiting for the agent" />
            )}
          </section>
        );
      })}
      {error && !isStreaming && (
        <div role="alert" className="flex items-start gap-2 rounded-xl bg-danger-soft p-3 text-sm text-danger">
          <AlertIcon className="mt-0.5 size-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      <div ref={end} />
    </div>
  );
}
