import type { Message } from "@langchain/langgraph-sdk";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Workspace } from "../components/Workspace";
import type { Analysis, ProgressEvent, Report, Schema } from "../contract";
import { initialProgress, reduceProgress, toTurns, type ChatSession, type RunProgress, type ThreadSummary } from "../conversation";
import type { DataSource } from "../data-api";
import { useDatasets } from "../datasets";
import { useUrlThread } from "../url-thread";
import { chartAnalysis, correctedAnalysis, countryAnalysis, fixtureReport, fixtureSchema, tableAnalysis } from "./data";

const params = new URLSearchParams(window.location.search);
const startEmpty = params.get("fixture") === "empty";
/** `&hold=1` freezes the live run mid-retry, for screenshots. */
const hold = params.has("hold");

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function fixtureDataSource(): DataSource {
  let schema: Schema = startEmpty ? { tables: [] } : fixtureSchema;
  let report: Report | null = startEmpty ? null : fixtureReport;
  const load = (s: Schema, r: Report) => {
    schema = s;
    report = r;
    return r;
  };
  return {
    getSchema: async () => {
      await wait(250);
      return schema;
    },
    getReport: async () => {
      await wait(100);
      return report;
    },
    loadSample: async () => {
      await wait(1200);
      return load(fixtureSchema, fixtureReport);
    },
    upload: async (files, onProgress) => {
      for (let i = 1; i <= 10; i++) {
        await wait(120);
        onProgress(i / 10);
      }
      await wait(900);
      const added = files.map((f) => f.name.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9]+/g, "_"));
      const tables = [
        ...schema.tables.filter((t) => !added.includes(t.name)),
        ...added.map((name, i) => ({
          name,
          comment: `Loaded from ${files[i]?.name ?? name}: 120 rows.`,
          columns: [
            { name: "id", type: "BIGINT", comment: "From CSV column id.", primary_key: true, references: null },
            { name: "value", type: "TEXT", comment: "From CSV column value.", primary_key: false, references: null },
          ],
        })),
      ];
      const r: Report = {
        tables: [
          ...(report?.tables.filter((t) => !added.includes(t.name)) ?? []),
          ...added.map((name, i) => ({
            name,
            source: files[i]?.name ?? name,
            rows: 120,
            primary_key: "id",
            rejected_rows: [{ line: 14, reason: "Expected 2 fields, found 3" }],
            rejected_row_count: 1,
            withheld: [],
          })),
        ],
        relationships: report?.relationships ?? [],
        rejected_relationships: report?.rejected_relationships ?? [],
      };
      return load({ tables }, r);
    },
    remove: async (table) => {
      await wait(400);
      return load(
        { tables: schema.tables.filter((t) => t.name !== table) },
        {
          tables: report?.tables.filter((t) => t.name !== table) ?? [],
          relationships: report?.relationships.filter((r) => r.table !== table && r.parent_table !== table) ?? [],
          rejected_relationships: report?.rejected_relationships ?? [],
        },
      );
    },
  };
}

const human = (id: string, content: string): Message => ({ id, type: "human", content });
const ai = (id: string, content: string, analysis: Analysis | null): Message => ({
  id,
  type: "ai",
  content,
  additional_kwargs: analysis ? { analysis } : {},
});

const history: Message[] = [
  human("h1", correctedAnalysis.question),
  ai(
    "a1",
    "**Sweet Sydney Spoonfuls** has the most reviews (31), and it buys sugar from **Southern Sweets Co.** The top five franchises each get their main ingredient from a different supplier, and three of them are flour or sugar suppliers.",
    correctedAnalysis,
  ),
  human("h2", chartAnalysis.question),
  ai(
    "a2",
    "Daily revenue ran between about **$1.6k and $3.1k** over the 17 days. It peaks every Saturday (May 4, 11), and the weekday trough is around $1.7k.",
    chartAnalysis,
  ),
  human("h3", tableAnalysis.question),
  ai(
    "a3",
    "Here are the amex transactions in time order. There are more than the 100 rows shown; ask for a count or a breakdown to cover all of them.",
    tableAnalysis,
  ),
];

const live: { question: string; analysis: Analysis; answer: string; events: ProgressEvent[] } = {
  question: countryAnalysis.question,
  analysis: countryAnalysis,
  answer:
    "The **USA** leads with **$9,472** in revenue, followed by Japan ($6,104) and Australia ($5,310). Together the top three account for about 59% of all sales.",
  events: [
    { step: "plan", status: "started" },
    { step: "plan", status: "done" },
    { step: "write_sql", status: "started" },
    { step: "write_sql", status: "done" },
    { step: "run_sql", status: "started" },
    { step: "run_sql", status: "failed", detail: 'Binder Error: Referenced column "country" not found in FROM clause' },
    { step: "write_sql", status: "started" },
    { step: "write_sql", status: "done" },
    { step: "run_sql", status: "started" },
    { step: "run_sql", status: "done" },
    { step: "respond", status: "started" },
  ],
};
const HOLD_AT = 7;

function useFixtureSession(): ChatSession {
  const [messages, setMessages] = useState<Message[]>(() => (startEmpty ? [] : history));
  const [progress, setProgress] = useState<RunProgress | null>(null);
  const [streaming, setStreaming] = useState(false);
  const cancelled = useRef(false);

  const run = useCallback(async (question: string, script: typeof live) => {
    cancelled.current = false;
    setStreaming(true);
    setMessages((m) => [...m, human(`h-${m.length}`, question)]);
    let p = initialProgress;
    setProgress(p);
    for (const [i, event] of script.events.entries()) {
      if (hold && i === HOLD_AT) return;
      await wait(700);
      if (cancelled.current) return;
      p = reduceProgress(p, event);
      setProgress(p);
    }
    const id = `a-${Date.now()}`;
    const words = script.answer.split(/(?<= )/);
    for (let n = 1; n <= words.length; n++) {
      await wait(45);
      if (cancelled.current) return;
      const text = words.slice(0, n).join("");
      setMessages((m) => [...m.filter((x) => x.id !== id), ai(id, text, null)]);
    }
    setMessages((m) => [...m.filter((x) => x.id !== id), ai(id, script.answer, script.analysis)]);
    setProgress(null);
    setStreaming(false);
  }, []);

  const started = useRef(false);
  useEffect(() => {
    if (startEmpty || started.current) return;
    started.current = true;
    void run(live.question, live);
  }, [run]);

  const submit = useCallback(
    (question: string) => {
      const analysis = { ...countryAnalysis, question };
      void run(question, {
        ...live,
        analysis,
        events: live.events.filter((e) => e.step !== "run_sql" || e.status !== "failed").slice(0, 8),
      });
    },
    [run],
  );

  const stop = useCallback(() => {
    cancelled.current = true;
    setStreaming(false);
    setProgress(null);
  }, []);

  const turns = useMemo(() => toTurns(messages), [messages]);
  return { turns, isStreaming: streaming, progress, error: null, submit, stop };
}

const ago = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();
const fixtureThreads: ThreadSummary[] = [
  { id: "fixture-1", title: correctedAnalysis.question, updatedAt: ago(0) },
  { id: "fixture-2", title: "Top customers by lifetime spend in Japan", updatedAt: ago(95) },
  { id: "fixture-3", title: "Which suppliers are not approved?", updatedAt: ago(60 * 26) },
];

const dataSource = fixtureDataSource();

export function FixtureApp() {
  const [threadId, selectThread] = useUrlThread();
  const session = useFixtureSession();
  const datasets = useDatasets(dataSource);
  return (
    <Workspace
      session={session}
      datasets={datasets}
      threads={startEmpty ? [] : fixtureThreads}
      threadId={threadId ?? (startEmpty ? null : "fixture-1")}
      onSelectThread={selectThread}
      onNewThread={() => {
        selectThread(null);
      }}
    />
  );
}
