import { useLayoutEffect, useRef, useState } from "react";
import { SendIcon, StopIcon } from "./icons";

export function Composer({
  streaming,
  onSubmit,
  onStop,
}: {
  streaming: boolean;
  onSubmit: (text: string) => void;
  onStop: () => void;
}) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  const send = () => {
    const q = text.trim();
    if (!q || streaming) return;
    onSubmit(q);
    setText("");
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
      className="flex items-end gap-2 rounded-2xl border border-line-strong bg-surface p-2 shadow-[0_2px_12px_rgb(0_0_0/0.06)] focus-within:border-accent"
    >
      <label htmlFor="question" className="sr-only">
        Ask a question about your data
      </label>
      <textarea
        id="question"
        ref={ref}
        rows={1}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            send();
          }
        }}
        placeholder="Ask a question about your data…"
        className="max-h-[200px] min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-6 text-ink outline-none placeholder:text-muted focus-visible:outline-none"
      />
      {streaming ? (
        <button
          type="button"
          onClick={onStop}
          aria-label="Stop generating"
          className="grid size-10 shrink-0 place-items-center rounded-xl bg-ink text-bg hover:opacity-90"
        >
          <StopIcon className="size-4" />
        </button>
      ) : (
        <button
          type="submit"
          aria-label="Send question"
          disabled={!text.trim()}
          className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent text-accent-ink hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <SendIcon className="size-5" strokeWidth={2.2} />
        </button>
      )}
    </form>
  );
}
