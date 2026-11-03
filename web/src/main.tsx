import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";

async function pickApp(): Promise<ReactNode> {
  // Dev-only fixture mode; `import.meta.env.DEV` is a build-time constant, so production drops this branch.
  if (import.meta.env.DEV && new URLSearchParams(window.location.search).has("fixture")) {
    const { FixtureApp } = await import("./fixture/FixtureApp");
    return <FixtureApp />;
  }
  const { App } = await import("./App");
  return <App />;
}

const root = document.getElementById("root");
if (!root) throw new Error("index.html is missing #root");
void pickApp().then((app) => {
  createRoot(root).render(<StrictMode>{app}</StrictMode>);
});
