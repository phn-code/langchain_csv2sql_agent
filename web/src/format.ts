import type { Cell, ColumnKind, QueryResult } from "./contract";

const integer = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const dateOnly = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function formatCount(n: number): string {
  return integer.format(n);
}

export function formatCell(value: Cell, kind: ColumnKind): string {
  if (value === null) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (kind === "number" && typeof value === "number") {
    return Number.isInteger(value) ? integer.format(value) : decimal.format(value);
  }
  if (kind === "temporal") {
    const date = new Date(typeof value === "number" ? value : value.replace(" ", "T"));
    if (Number.isNaN(date.getTime())) return String(value);
    const time = typeof value === "string" ? /[T ](\d{2}:\d{2})/.exec(value)?.[1] : undefined;
    const hasTime = time !== undefined && time !== "00:00";
    return hasTime ? dateTime.format(date) : dateOnly.format(date);
  }
  return String(value);
}

function csvField(value: Cell): string {
  if (value === null) return "";
  const s = String(value);
  return /[",\n\r]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

export function toCsv(result: QueryResult): string {
  const lines = [result.columns.map((c) => csvField(c.name)).join(",")];
  for (const row of result.rows) lines.push(row.map(csvField).join(","));
  return lines.join("\r\n") + "\r\n";
}

export function downloadText(filename: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function slugify(text: string): string {
  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 48) || "result"
  );
}

export function relativeTime(iso: string): string {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (seconds < 60) return "just now";
  if (seconds < 3600) return rtf.format(-Math.round(seconds / 60), "minute");
  if (seconds < 86400) return rtf.format(-Math.round(seconds / 3600), "hour");
  return rtf.format(-Math.round(seconds / 86400), "day");
}

export function rowSummary(result: QueryResult): string {
  const n = formatCount(result.rows.length);
  const noun = result.rows.length === 1 ? "row" : "rows";
  return result.truncated ? `Showing first ${n} ${noun} (truncated)` : `${n} ${noun}`;
}
