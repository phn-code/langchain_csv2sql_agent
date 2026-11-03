import type { Relationship, Report, Schema, SchemaColumn } from "./contract";

export type ColumnRef = { table: string; column: string };

export type ExplorerColumn = SchemaColumn & {
  target: ColumnRef | null;
  /** How the backend matched this foreign key, when the ingest report knows. */
  link: Pick<Relationship, "offset" | "origin"> | null;
};

export type ExplorerTable = {
  name: string;
  rows: number | null;
  source: string | null;
  note: string | null;
  withheld: { column: string; pii: string }[];
  columns: ExplorerColumn[];
  referencedBy: (ColumnRef & { via: string })[];
};

const REF = /^\s*([^()\s]+)\s*\(\s*([^()\s]+)\s*\)\s*$/;

export function parseReference(ref: string | null): ColumnRef | null {
  const m = ref ? REF.exec(ref) : null;
  return m?.[1] && m[2] ? { table: m[1], column: m[2] } : null;
}

/**
 * Splits a table comment like "Loaded from x.csv: 300 rows. Withheld for privacy: first_name (person name), ..."
 * Used only when the ingest report doesn't cover the table.
 */
function parseTableComment(comment: string | null) {
  if (!comment) return { rows: null, source: null, withheld: [], note: null };
  const [head = "", withheldPart] = comment.split(/Withheld for privacy:/i);
  const loaded = /Loaded from\s+(\S+?):\s*([\d,]+)\s+rows?\.?/i.exec(head);
  const withheld = (withheldPart ?? "")
    .split(/,(?![^()]*\))/)
    .map((s) => /^\s*([^\s(]+)\s*(?:\(([^)]*)\))?/.exec(s.replace(/\.\s*$/, "")))
    .flatMap((m) => (m?.[1] ? [{ column: m[1], pii: m[2] ?? "personal data" }] : []));
  const note = (loaded ? head.replace(loaded[0], "") : head).trim() || null;
  return {
    rows: loaded?.[2] ? Number(loaded[2].replaceAll(",", "")) : null,
    source: loaded?.[1] ?? null,
    withheld,
    note,
  };
}

export function buildExplorer(schema: Schema, report: Report | null): ExplorerTable[] {
  const reportTables = new Map(report?.tables.map((t) => [t.name, t]));
  const links = new Map(report?.relationships.map((r) => [`${r.table}.${r.column}`, r]));
  const incoming = new Map<string, ExplorerTable["referencedBy"]>();

  const tables = schema.tables.map((t): ExplorerTable => {
    const fromComment = parseTableComment(t.comment);
    const fromReport = reportTables.get(t.name);
    const columns = t.columns.map((c): ExplorerColumn => {
      const target = parseReference(c.references);
      if (target) {
        const list = incoming.get(target.table) ?? [];
        list.push({ table: t.name, column: target.column, via: c.name });
        incoming.set(target.table, list);
      }
      const link = links.get(`${t.name}.${c.name}`);
      return { ...c, target, link: link ? { offset: link.offset, origin: link.origin } : null };
    });
    return {
      name: t.name,
      rows: fromReport?.rows ?? fromComment.rows,
      source: fromReport?.source ?? fromComment.source,
      withheld: fromReport?.withheld ?? fromComment.withheld,
      note: fromComment.note,
      columns,
      referencedBy: [],
    };
  });
  for (const t of tables) t.referencedBy = incoming.get(t.name) ?? [];
  return tables;
}

/** Strips the boilerplate "From CSV column X." prefix so the meaningful part of a column comment leads. */
export function columnNote(comment: string | null): { origin: string | null; note: string | null } {
  if (!comment) return { origin: null, note: null };
  const m = /^From CSV column\s+(.+?)\.(?:\s+|$)/.exec(comment);
  return m ? { origin: m[1] ?? null, note: comment.slice(m[0].length).trim() || null } : { origin: null, note: comment };
}
