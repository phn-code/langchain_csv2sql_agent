"""`csv2sql-eval`: execution accuracy against the sample data.

A case passes when the agent's result holds the same rows as the reference query's result. Columns are matched by
content, not name or position, and extra columns are allowed, so `SELECT product, sum(x) AS revenue` and
`SELECT sum(x) total, product` both pass. Row order matters only for cases marked `ordered`.
"""

import argparse
import asyncio
import itertools
import json
import time
import tomllib
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from csv2sql.agent.graph import build_graph
from csv2sql.database import Database, Json, QueryResult
from csv2sql.settings import Settings

CASES = Path(__file__).resolve().parents[2] / "evals" / "cases.toml"


@dataclass(frozen=True)
class Case:
    id: str
    turns: list[str]
    sql: str
    ordered: bool = False


@dataclass(frozen=True)
class Outcome:
    id: str
    passed: bool
    sql: str | None
    corrections: int
    seconds: float
    error: str | None = None


def _normalize(value: Json) -> Json:
    if isinstance(value, float):
        return int(value) if value.is_integer() else round(value, 2)
    if isinstance(value, str) and len(value) >= 19 and value[10] == "T":
        # Timestamps compare to the second whatever the offset formatting; midnight compares equal to a date.
        return value[:10] if value[10:19] == "T00:00:00" else value[:19]
    return value


def results_match(expected: QueryResult, actual: QueryResult, *, ordered: bool) -> bool:
    if len(expected["rows"]) != len(actual["rows"]):
        return False

    def column(result: QueryResult, i: int) -> list[Json]:
        return [_normalize(row[i]) for row in result["rows"]]

    def as_multiset(values: Sequence[Json]) -> Counter[str]:
        return Counter(map(repr, values))

    width = len(actual["columns"])
    candidates = [
        [j for j in range(width) if as_multiset(column(actual, j)) == as_multiset(column(expected, i))]
        for i in range(len(expected["columns"]))
    ]
    for mapping in itertools.product(*candidates):
        if len(set(mapping)) != len(mapping):
            continue
        want = [tuple(_normalize(row[i]) for i in range(len(mapping))) for row in expected["rows"]]
        got = [tuple(_normalize(row[j]) for j in mapping) for row in actual["rows"]]
        if want == got if ordered else Counter(map(repr, want)) == Counter(map(repr, got)):
            return True
    return False


def load_cases(path: Path) -> list[Case]:
    data = tomllib.loads(path.read_text())
    return [
        Case(id=c["id"], turns=c.get("turns") or [c["question"]], sql=c["sql"], ordered=c.get("ordered", False))
        for c in data["case"]
    ]


async def run_case(graph: Any, database: Database, case: Case) -> Outcome:
    started = time.perf_counter()
    messages: list[AnyMessage] = []
    try:
        for turn in case.turns:
            state = await graph.ainvoke({"messages": [*messages, HumanMessage(turn)]})
            messages = state["messages"]
        final = messages[-1]
        analysis: dict[str, Any] = {}
        if isinstance(final, AIMessage):
            analysis = final.additional_kwargs.get("analysis") or {}
        expected = await database.query(case.sql)
        actual = analysis.get("result")
        passed = actual is not None and results_match(expected, actual, ordered=case.ordered)
        return Outcome(case.id, passed, analysis.get("sql"), len(analysis.get("failures", [])), _since(started))
    except Exception as error:
        return Outcome(case.id, False, None, 0, _since(started), f"{type(error).__name__}: {error}")


def _since(started: float) -> float:
    return round(time.perf_counter() - started, 2)


async def evaluate(model_name: str, cases: list[Case], concurrency: int) -> list[Outcome]:
    settings = Settings()  # type: ignore[call-arg]
    database = Database(str(settings.reader_database_url), max_rows=5_000, statement_timeout_ms=10_000)
    graph = build_graph(init_chat_model(model_name), database, max_attempts=settings.max_sql_attempts)
    gate = asyncio.Semaphore(concurrency)

    async def bounded(case: Case) -> Outcome:
        async with gate:
            outcome = await run_case(graph, database, case)
            print(f"{'PASS' if outcome.passed else 'FAIL'}  {case.id:32} {outcome.seconds:6.1f}s", flush=True)
            return outcome

    try:
        return await asyncio.gather(*(bounded(c) for c in cases))
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=Settings().model)  # type: ignore[call-arg]
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--only", nargs="*", help="Case ids to run.")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--out", type=Path, default=Path("evals/results"))
    args = parser.parse_args()

    cases = [c for c in load_cases(args.cases) if not args.only or c.id in args.only]
    outcomes = asyncio.run(evaluate(args.model, cases, args.concurrency))
    passed = sum(o.passed for o in outcomes)
    corrected = sum(o.passed and o.corrections > 0 for o in outcomes)
    share = passed / len(outcomes)
    print(f"\n{args.model}: {passed}/{len(outcomes)} passed ({share:.0%}), {corrected} after self-correction")
    for o in outcomes:
        if not o.passed:
            print(f"  {o.id}: {o.error or o.sql}")

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = args.out / f"{stamp}-{args.model.replace(':', '_')}.json"
    path.write_text(json.dumps({"model": args.model, "outcomes": [asdict(o) for o in outcomes]}, indent=2))
    print(f"Wrote {path}")
