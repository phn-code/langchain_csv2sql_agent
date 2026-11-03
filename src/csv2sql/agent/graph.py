"""plan -> write_sql <-> run_sql -> respond.

Only `respond` streams tokens to the user; the structured calls are tagged `langsmith:nostream`. Each step emits
a custom progress event so a UI can show what the agent is doing.
"""

from collections.abc import Sequence
from typing import Any, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from csv2sql.agent import prompts
from csv2sql.charts import ChartKind, build_chart
from csv2sql.database import Database, QueryError, QueryResult
from csv2sql.guard import RejectedQuery, check_query

HISTORY_MESSAGES = 12
PREVIEW_ROWS = 40
PAYLOAD_ROWS = 200

type Step = Literal["plan", "write_sql", "run_sql", "respond"]


class Failure(TypedDict):
    sql: str
    error: str


class State(MessagesState):
    question: str
    action: Literal["query", "reply"]
    chart: ChartKind
    schema: str
    tables: list[str]
    failures: list[Failure]
    sql: str | None
    result: QueryResult | None


class Plan(BaseModel):
    action: Literal["query", "reply"]
    question: str = Field(description="The latest request as a complete, standalone question.")
    chart: ChartKind


class SqlDraft(BaseModel):
    plan: str = Field(description="One or two sentences: tables, joins, filters, grouping.")
    sql: str = Field(description="One PostgreSQL SELECT statement.")


def _progress(step: Step, status: Literal["started", "done", "failed"], detail: str | None = None) -> None:
    event: dict[str, Any] = {"step": step, "status": status}
    if detail:
        event["detail"] = detail
    get_stream_writer()(event)


def _text(message: AnyMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return " ".join(part["text"] for part in message.content if isinstance(part, dict) and part.get("type") == "text")


def _analysis(message: AnyMessage) -> dict[str, Any] | None:
    return message.additional_kwargs.get("analysis") if isinstance(message, AIMessage) else None


def _history(messages: Sequence[AnyMessage]) -> str:
    lines: list[str] = []
    for message in messages[-HISTORY_MESSAGES:]:
        if isinstance(message, HumanMessage):
            lines.append(f"User: {_text(message)}")
        elif isinstance(message, AIMessage):
            lines.append(f"Assistant: {_text(message)}")
            if (analysis := _analysis(message)) and analysis.get("sql"):
                lines.append(f"(Assistant's SQL: {' '.join(analysis['sql'].split())})")
    return "\n".join(lines) or "(none)"


def _previous_sql(messages: Sequence[AnyMessage]) -> str | None:
    for message in reversed(messages):
        if (analysis := _analysis(message)) and analysis.get("sql"):
            return analysis["sql"]
    return None


def _table(result: QueryResult, limit: int) -> str:
    header = ",".join(c["name"] for c in result["columns"])
    body = [",".join("" if v is None else str(v) for v in row) for row in result["rows"][:limit]]
    more = [f"... {len(result['rows']) - limit} more rows"] if len(result["rows"]) > limit else []
    return "\n".join([header, *body, *more])


def _attempts(failures: Sequence[Failure]) -> str:
    return "\n\n".join(f"Attempt {i}:\n{f['sql']}\nError: {f['error']}" for i, f in enumerate(failures, 1))


def build_graph(model: BaseChatModel, database: Database, *, max_attempts: int = 3) -> CompiledStateGraph[Any]:
    planner = model.with_structured_output(Plan).with_config(tags=["langsmith:nostream"], run_name="plan")
    writer = model.with_structured_output(SqlDraft).with_config(tags=["langsmith:nostream"], run_name="write_sql")

    async def plan(state: State) -> dict[str, Any]:
        _progress("plan", "started")
        catalog = await database.catalog()
        schema = catalog.render() or prompts.EMPTY_SCHEMA
        decision = await planner.ainvoke(prompts.PLAN.format(schema=schema, history=_history(state["messages"])))
        assert isinstance(decision, Plan)
        action = decision.action if catalog.tables else "reply"
        _progress("plan", "done", decision.question)
        return {
            "question": decision.question,
            "action": action,
            "chart": decision.chart,
            "schema": schema,
            "tables": sorted(catalog.table_names),
            "failures": [],
            "sql": None,
            "result": None,
        }

    async def write_sql(state: State) -> dict[str, Any]:
        _progress("write_sql", "started")
        previous = _previous_sql(state["messages"][:-1])
        draft = await writer.ainvoke(
            prompts.WRITE_SQL.format(
                schema=state["schema"],
                chart_rule=prompts.CHART_RULE if state["chart"] != "none" else "",
                question=state["question"],
                previous=prompts.PREVIOUS_SQL.format(sql=previous) if previous else "",
                failures=prompts.FAILURES.format(attempts=_attempts(state["failures"])) if state["failures"] else "",
            )
        )
        assert isinstance(draft, SqlDraft)
        _progress("write_sql", "done", draft.plan)
        return {"sql": draft.sql}

    async def run_sql(state: State) -> dict[str, Any]:
        _progress("run_sql", "started")
        sql = state["sql"] or ""
        try:
            statement = check_query(sql, state["tables"])
            result = await database.query(statement)
        except (RejectedQuery, QueryError) as error:
            _progress("run_sql", "failed", str(error))
            return {"failures": [*state["failures"], {"sql": sql, "error": str(error)}], "sql": None}
        _progress("run_sql", "done", f"{len(result['rows'])} rows in {result['elapsed_ms']} ms")
        return {"sql": statement, "result": result}

    async def respond(state: State) -> dict[str, Any]:
        _progress("respond", "started")
        result = state.get("result")
        chart = build_chart(state["chart"], result, state["question"]) if result else None
        if result is not None and state["sql"]:
            context = prompts.RESULT_CONTEXT.format(
                sql=state["sql"],
                row_count=len(result["rows"]),
                truncated=", truncated" if result["truncated"] else "",
                table=_table(result, PREVIEW_ROWS),
            )
        elif state["failures"]:
            context = prompts.FAILED_CONTEXT.format(attempts=_attempts(state["failures"]))
        else:
            context = prompts.NO_QUERY_CONTEXT.format(schema=state["schema"], history=_history(state["messages"]))
        message = await model.ainvoke(
            prompts.RESPOND.format(
                question=state["question"],
                context=context,
                chart_note=" and a chart" if chart else "",
            ),
            config={"run_name": "respond"},
        )
        answer = AIMessage(content=message.content, id=message.id)
        if state["action"] == "query":
            payload_result = {**result, "rows": result["rows"][:PAYLOAD_ROWS]} if result else None
            answer.additional_kwargs["analysis"] = {
                "question": state["question"],
                "sql": state["sql"],
                "result": payload_result,
                "chart": chart,
                "failures": state["failures"],
            }
        _progress("respond", "done")
        return {"messages": [answer]}

    def after_plan(state: State) -> Literal["write_sql", "respond"]:
        return "write_sql" if state["action"] == "query" else "respond"

    def after_run(state: State) -> Literal["write_sql", "respond"]:
        if state["result"] is None and len(state["failures"]) < max_attempts:
            return "write_sql"
        return "respond"

    graph = StateGraph(State)
    graph.add_node(plan)
    graph.add_node(write_sql)
    graph.add_node(run_sql)
    graph.add_node(respond)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", after_plan)
    graph.add_edge("write_sql", "run_sql")
    graph.add_conditional_edges("run_sql", after_run)
    graph.add_edge("respond", END)
    return graph.compile()
