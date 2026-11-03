import { useEffect, useRef, useState } from "react";
import type { ResolvedTheme } from "../theme";

function themeConfig(): Record<string, unknown> {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string) => css.getPropertyValue(name).trim();
  const font = v("--font-sans") || "system-ui";
  const range = [1, 2, 3, 4, 5, 6].map((i) => v(`--chart-${i}`));
  const axis = {
    domainColor: v("--line-strong"),
    gridColor: v("--line"),
    tickColor: v("--line-strong"),
    labelColor: v("--muted"),
    titleColor: v("--ink-2"),
    labelFont: font,
    titleFont: font,
    labelFontSize: 11,
    titleFontSize: 11,
    titleFontWeight: 600,
  };
  return {
    background: "transparent",
    font,
    view: { stroke: "transparent" },
    axis,
    axisX: { grid: false },
    axisY: { gridDash: [2, 3], domain: false, ticks: false },
    axisBand: { grid: false },
    legend: { labelColor: v("--ink-2"), titleColor: v("--ink-2"), labelFont: font, titleFont: font },
    title: { color: v("--ink"), font, fontSize: 13, fontWeight: 600, anchor: "start" },
    header: { labelColor: v("--ink-2"), titleColor: v("--ink-2") },
    range: { category: range },
    mark: { color: range[0] },
    bar: { color: range[0], cornerRadiusEnd: 3 },
    line: { color: range[0], strokeWidth: 2 },
    area: { color: range[0], opacity: 0.85 },
    point: { color: range[0], filled: true },
  };
}

export default function ChartView({ spec, theme }: { spec: Record<string, unknown>; theme: ResolvedTheme }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let finalize: (() => void) | undefined;
    const abort = new AbortController();
    const aborted = () => abort.signal.aborted;
    void import("vega-embed").then(async ({ default: embed }) => {
      if (aborted()) return;
      const sized = { width: "container", height: 280, autosize: { type: "fit-x", contains: "padding" }, ...spec };
      try {
        const result = await embed(el, sized as Parameters<typeof embed>[1], {
          actions: { export: true, source: false, compiled: false, editor: false },
          config: themeConfig(),
          renderer: "svg",
          tooltip: { theme: theme === "dark" ? "dark" : "light" },
        });
        if (aborted()) result.finalize();
        else finalize = () => {
          result.finalize();
        };
      } catch (e) {
        if (!aborted()) setError(e instanceof Error ? e.message : "Chart failed to render");
      }
    });
    return () => {
      abort.abort();
      finalize?.();
    };
  }, [spec, theme]);

  if (error) {
    return <p className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">Couldn't render this chart: {error}</p>;
  }
  return <div ref={ref} className="min-h-[280px] w-full" role="img" aria-label="Chart of the query result" />;
}
