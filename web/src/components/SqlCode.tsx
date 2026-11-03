import { useState, type ReactNode } from "react";
import { CopyIcon, CheckIcon } from "./icons";

const KEYWORDS = new Set(
  `select from where group by order having limit offset join left right inner outer full cross on as and or not
  in is null like ilike between case when then else end distinct union all with asc desc over partition
  insert update delete into values create table view exists cast true false filter within interval`
    .split(/\s+/)
    .filter(Boolean),
);

const TOKEN = /(--[^\n]*)|('(?:[^']|'')*')|("(?:[^"]|"")*")|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)(\s*\()?|([\s\S])/g;

/** A deliberately small SQL highlighter: comments, strings, numbers, keywords, function calls. */
function highlightSql(sql: string): ReactNode[] {
  const out: ReactNode[] = [];
  let plain = "";
  const flush = () => {
    if (plain) out.push(plain);
    plain = "";
  };
  const push = (cls: string, text: string) => {
    flush();
    out.push(
      <span key={out.length} className={cls}>
        {text}
      </span>,
    );
  };
  for (const m of sql.matchAll(TOKEN)) {
    const [, comment, str, quoted, num, word, call] = m;
    if (comment) push("tok-com", comment);
    else if (str) push("tok-str", str);
    else if (quoted) plain += quoted;
    else if (num) push("tok-num", num);
    else if (word) {
      if (KEYWORDS.has(word.toLowerCase())) push("tok-kw", word);
      else if (call) push("tok-fn", word);
      else plain += word;
      if (call) plain += call;
    } else plain += m[0];
  }
  flush();
  return out;
}

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      aria-label={copied ? "Copied" : label}
      title={label}
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => {
            setCopied(false);
          }, 1500);
        });
      }}
      className="inline-flex items-center gap-1.5 rounded-md border border-line bg-surface px-2 py-1 text-xs font-medium text-ink-2 hover:border-line-strong hover:text-ink"
    >
      {copied ? <CheckIcon className="size-3.5 text-ok" /> : <CopyIcon className="size-3.5" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export function SqlCode({ sql, tone = "default" }: { sql: string; tone?: "default" | "failed" }) {
  return (
    <pre
      className={`overflow-x-auto rounded-lg border p-3 font-mono text-[12.5px] leading-relaxed ${
        tone === "failed" ? "border-danger/30 bg-danger-soft/40 text-ink-2" : "border-line bg-surface-2 text-ink"
      }`}
    >
      <code>{highlightSql(sql.trim())}</code>
    </pre>
  );
}
