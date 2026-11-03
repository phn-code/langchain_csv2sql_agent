import { useCallback, useEffect, useState } from "react";
import type { Report, Schema } from "./contract";
import type { DataSource } from "./data-api";

export type SchemaState =
  | { kind: "loading" }
  | { kind: "ready"; schema: Schema }
  | { kind: "error"; message: string };

export type UploadState =
  | { kind: "idle" }
  | { kind: "uploading"; files: string[]; fraction: number }
  | { kind: "processing"; files: string[] }
  | { kind: "error"; message: string };

const MAX_BYTES = 50 * 1024 * 1024;

/** Client-side pre-check so obvious mistakes fail fast; the data API stays the authority. */
function checkFiles(files: File[]): string | null {
  if (files.length === 0) return "Choose at least one CSV file.";
  const wrong = files.find((f) => !/\.(csv|tsv|txt)$/i.test(f.name));
  if (wrong) return `${wrong.name} isn't a .csv, .tsv or .txt file.`;
  const big = files.find((f) => f.size > MAX_BYTES);
  if (big) return `${big.name} is over the 50 MB limit.`;
  return null;
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

type Snapshot = { schema: SchemaState; report?: Report | null };

async function snapshot(source: DataSource): Promise<Snapshot> {
  try {
    const [schema, report] = await Promise.all([source.getSchema(), source.getReport()]);
    return { schema: { kind: "ready", schema }, report };
  } catch (e) {
    return { schema: { kind: "error", message: message(e) } };
  }
}

export function useDatasets(source: DataSource) {
  const [schema, setSchema] = useState<SchemaState>({ kind: "loading" });
  const [report, setReport] = useState<Report | null>(null);
  const [upload, setUpload] = useState<UploadState>({ kind: "idle" });
  /** The report the user should see now: set after an ingest, cleared when they dismiss it. */
  const [shownReport, setShownReport] = useState<Report | null>(null);

  const apply = useCallback((snapshot: Snapshot) => {
    setSchema(snapshot.schema);
    if (snapshot.report !== undefined) setReport(snapshot.report);
  }, []);

  const refresh = useCallback(async () => {
    apply(await snapshot(source));
  }, [apply, source]);

  useEffect(() => {
    let current = true;
    void snapshot(source).then((s) => {
      if (current) apply(s);
    });
    return () => {
      current = false;
    };
  }, [apply, source]);

  const ingest = useCallback(
    async (run: () => Promise<Report>) => {
      try {
        const r = await run();
        setReport(r);
        setShownReport(r);
        setUpload({ kind: "idle" });
        await refresh();
      } catch (e) {
        setUpload({ kind: "error", message: message(e) });
      }
    },
    [refresh],
  );

  const uploadFiles = useCallback(
    (files: File[]) => {
      const problem = checkFiles(files);
      if (problem) {
        setUpload({ kind: "error", message: problem });
        return Promise.resolve();
      }
      const names = files.map((f) => f.name);
      setUpload({ kind: "uploading", files: names, fraction: 0 });
      return ingest(() =>
        source.upload(files, (fraction) => {
          setUpload(fraction < 1 ? { kind: "uploading", files: names, fraction } : { kind: "processing", files: names });
        }),
      );
    },
    [ingest, source],
  );

  const loadSample = useCallback(() => {
    setUpload({ kind: "processing", files: ["Bakery sample data"] });
    return ingest(() => source.loadSample());
  }, [ingest, source]);

  const removeTable = useCallback(
    async (table: string) => {
      try {
        setReport(await source.remove(table));
        await refresh();
      } catch (e) {
        setUpload({ kind: "error", message: message(e) });
      }
    },
    [refresh, source],
  );

  return {
    schema,
    report,
    upload,
    shownReport,
    showReport: setShownReport,
    dismissError: () => {
      setUpload({ kind: "idle" });
    },
    uploadFiles,
    loadSample,
    removeTable,
    refresh,
  };
}

export type Datasets = ReturnType<typeof useDatasets>;
