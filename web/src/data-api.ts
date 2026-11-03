import type { z } from "zod";
import {
  datasetsResponse,
  errorResponse,
  reportResponse,
  schemaResponse,
  type Report,
  type Schema,
} from "./contract";

export type DataSource = {
  getSchema: () => Promise<Schema>;
  getReport: () => Promise<Report | null>;
  upload: (files: File[], onProgress: (fraction: number) => void) => Promise<Report>;
  remove: (table: string) => Promise<Report>;
  loadSample: () => Promise<Report>;
};

export class DataApiError extends Error {}

function decode<T>(schema: z.ZodType<T>, status: number, body: unknown): T {
  if (status >= 200 && status < 300) {
    const parsed = schema.safeParse(body);
    if (parsed.success) return parsed.data;
    throw new DataApiError("The data API returned an unexpected response.");
  }
  const err = errorResponse.safeParse(body);
  if (err.success) throw new DataApiError(err.data.error);
  if (status === 413) throw new DataApiError("That file is too large (the limit is 50 MB per file).");
  throw new DataApiError(`The data API responded with HTTP ${status}.`);
}

async function request<T>(schema: z.ZodType<T>, url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new DataApiError(`Can't reach the data API at ${url}.`);
  }
  const body: unknown = await res.json().catch(() => null);
  return decode(schema, res.status, body);
}

export function httpDataSource(baseUrl: string): DataSource {
  const base = baseUrl.replace(/\/$/, "");
  return {
    getSchema: () => request(schemaResponse, `${base}/schema`),
    getReport: async () => (await request(datasetsResponse, `${base}/datasets`)).report,
    remove: async (table) =>
      (await request(reportResponse, `${base}/datasets/${encodeURIComponent(table)}`, { method: "DELETE" }))
        .report,
    loadSample: async () => (await request(reportResponse, `${base}/datasets/sample`, { method: "POST" })).report,
    // XHR rather than fetch: fetch exposes no upload progress.
    upload: (files, onProgress) =>
      new Promise((resolve, reject) => {
        const form = new FormData();
        for (const f of files) form.append("files", f);
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${base}/datasets`);
        xhr.responseType = "json";
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress(e.loaded / e.total);
        };
        xhr.onerror = () => {
          reject(new DataApiError(`Can't reach the data API at ${base}.`));
        };
        xhr.onload = () => {
          try {
            resolve(decode(reportResponse, xhr.status, xhr.response).report);
          } catch (e) {
            reject(e instanceof Error ? e : new DataApiError(String(e)));
          }
        };
        xhr.send(form);
      }),
  };
}
