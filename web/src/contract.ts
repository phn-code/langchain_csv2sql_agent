import { z } from "zod";

const cell = z.union([z.string(), z.number(), z.boolean(), z.null()]);

const columnKind = z.enum(["number", "temporal", "text"]);

const resultSchema = z.object({
  columns: z.array(z.object({ name: z.string(), kind: columnKind })),
  rows: z.array(z.array(cell)),
  truncated: z.boolean(),
  elapsed_ms: z.number(),
});

const analysisSchema = z.object({
  question: z.string(),
  sql: z.string().nullable(),
  result: resultSchema.nullable(),
  chart: z.record(z.string(), z.unknown()).nullable(),
  failures: z.array(z.object({ sql: z.string(), error: z.string() })),
});

export type Cell = z.infer<typeof cell>;
export type ColumnKind = z.infer<typeof columnKind>;
export type QueryResult = z.infer<typeof resultSchema>;
export type Analysis = z.infer<typeof analysisSchema>;

export function parseAnalysis(kwargs: Record<string, unknown> | undefined): Analysis | null {
  const parsed = analysisSchema.safeParse(kwargs?.analysis);
  return parsed.success ? parsed.data : null;
}

export const stepNames = ["plan", "write_sql", "run_sql", "respond"] as const;
export type StepName = (typeof stepNames)[number];

const progressEventSchema = z.object({
  step: z.enum(stepNames),
  status: z.enum(["started", "done", "failed"]),
  detail: z.string().optional(),
});
export type ProgressEvent = z.infer<typeof progressEventSchema>;

export function parseProgressEvent(data: unknown): ProgressEvent | null {
  const parsed = progressEventSchema.safeParse(data);
  return parsed.success ? parsed.data : null;
}

const schemaColumn = z.object({
  name: z.string(),
  type: z.string(),
  comment: z.string().nullable(),
  primary_key: z.boolean(),
  references: z.string().nullable(),
});

export const schemaResponse = z.object({
  tables: z.array(
    z.object({ name: z.string(), comment: z.string().nullable(), columns: z.array(schemaColumn) }),
  ),
});
export type Schema = z.infer<typeof schemaResponse>;
export type SchemaTable = Schema["tables"][number];
export type SchemaColumn = z.infer<typeof schemaColumn>;

const reportSchema = z.object({
  tables: z.array(
    z.object({
      name: z.string(),
      source: z.string(),
      rows: z.number(),
      primary_key: z.string().nullable(),
      rejected_rows: z.array(z.object({ line: z.number(), reason: z.string() })),
      rejected_row_count: z.number(),
      withheld: z.array(z.object({ column: z.string(), pii: z.string() })),
    }),
  ),
  relationships: z.array(
    z.object({
      table: z.string(),
      column: z.string(),
      parent_table: z.string(),
      parent_column: z.string(),
      offset: z.number(),
      origin: z.enum(["name", "ai"]),
    }),
  ),
  rejected_relationships: z.array(
    z.object({ table: z.string(), column: z.string(), parent_table: z.string(), reason: z.string() }),
  ),
});
export type Report = z.infer<typeof reportSchema>;
export type ReportTable = Report["tables"][number];
export type Relationship = Report["relationships"][number];

export const datasetsResponse = z.object({ report: reportSchema.nullable() });
export const reportResponse = z.object({ report: reportSchema });
export const errorResponse = z.object({ error: z.string() });
