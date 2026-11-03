from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from csv2sql.agent.graph import Plan, SqlDraft, build_graph
from csv2sql.database import Database

from .conftest import MakeDatabase
from .scripted import ScriptedModel

DAILY = (
    "SELECT date_trunc('day', date_time) AS day, sum(total_price) AS revenue "
    "FROM sales_transactions GROUP BY 1 ORDER BY 1"
)


@pytest.fixture
async def db(sample_db: tuple[str, str]):
    database = Database(sample_db[1], max_rows=500, statement_timeout_ms=2000)
    yield database
    await database.close()


async def run(model: ScriptedModel, db: Database, messages: list[Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    graph = build_graph(model, db)
    events: list[dict[str, Any]] = []
    state: dict[str, Any] = {}
    async for mode, chunk in graph.astream({"messages": messages}, stream_mode=["custom", "values"]):
        assert isinstance(chunk, dict)
        if mode == "custom":
            events.append(chunk)
        else:
            state = chunk
    return state, events


def analysis(state: dict[str, Any]) -> dict[str, Any]:
    message = state["messages"][-1]
    assert isinstance(message, AIMessage)
    return message.additional_kwargs["analysis"]


async def test_answers_with_rows_and_a_chart(db: Database) -> None:
    model = ScriptedModel(
        script=[
            Plan(action="query", question="What was revenue per day?", chart="auto"),
            SqlDraft(plan="Sum total_price per day.", sql=DAILY),
            "Revenue was highest on May 3.",
        ]
    )
    state, events = await run(model, db, [HumanMessage("plot daily revenue")])

    payload = analysis(state)
    assert payload["sql"] == DAILY
    assert payload["failures"] == []
    assert [c["name"] for c in payload["result"]["columns"]] == ["day", "revenue"]
    assert sum(row[1] for row in payload["result"]["rows"]) == 66_471
    assert payload["chart"]["mark"]["type"] == "line"
    assert state["messages"][-1].content == "Revenue was highest on May 3."
    assert [(e["step"], e["status"]) for e in events] == [
        ("plan", "started"), ("plan", "done"),
        ("write_sql", "started"), ("write_sql", "done"),
        ("run_sql", "started"), ("run_sql", "done"),
        ("respond", "started"), ("respond", "done"),
    ]  # fmt: skip
    assert "customer_id bigint REFERENCES sales_customers(customer_id)" in model.prompts[1]
    assert "The result will be drawn as a chart" in model.prompts[1]


async def test_corrects_itself_from_guard_and_database_errors(db: Database) -> None:
    model = ScriptedModel(
        script=[
            Plan(action="query", question="How many customers are there?", chart="none"),
            SqlDraft(plan="Count.", sql="SELECT count(*) FROM customers"),
            SqlDraft(plan="Count.", sql="SELECT count(email_address) FROM sales_customers"),
            SqlDraft(plan="Count.", sql="SELECT count(*) AS customers FROM sales_customers"),
            "There are 300 customers.",
        ]
    )
    state, events = await run(model, db, [HumanMessage("how many customers?")])

    payload = analysis(state)
    assert payload["result"]["rows"] == [[300]]
    assert [f["error"] for f in payload["failures"]] == [
        "Unknown table `customers`. Available tables: media_customer_reviews, media_gold_reviews_chunked, "
        "sales_customers, sales_franchises, sales_suppliers, sales_transactions.",
        'column "email_address" does not exist',
    ]
    assert "Unknown table `customers`" in model.prompts[3]
    assert 'column "email_address" does not exist' in model.prompts[3]
    assert [e["status"] for e in events if e["step"] == "run_sql"] == ["started", "failed"] * 2 + ["started", "done"]


async def test_gives_up_after_the_attempt_budget(db: Database) -> None:
    model = ScriptedModel(
        script=[
            Plan(action="query", question="q", chart="none"),
            *[SqlDraft(plan="p", sql="SELECT nope FROM sales_customers") for _ in range(3)],
            "I could not answer that.",
        ]
    )
    state, _ = await run(model, db, [HumanMessage("q")])
    payload = analysis(state)
    assert payload["sql"] is None
    assert payload["result"] is None
    assert len(payload["failures"]) == 3
    assert "Every attempt to query the database failed" in model.prompts[-1]


async def test_replies_without_querying(db: Database) -> None:
    model = ScriptedModel(
        script=[Plan(action="reply", question="What data is there?", chart="none"), "There are six tables."]
    )
    state, events = await run(model, db, [HumanMessage("what can you do?")])
    assert "analysis" not in state["messages"][-1].additional_kwargs
    assert {e["step"] for e in events} == {"plan", "respond"}
    assert "No query was run" in model.prompts[-1]


async def test_follow_up_sees_the_previous_query(db: Database) -> None:
    first = ScriptedModel(
        script=[
            Plan(action="query", question="Revenue by payment method?", chart="none"),
            SqlDraft(plan="p", sql="SELECT payment_method, sum(total_price) FROM sales_transactions GROUP BY 1"),
            "Visa leads.",
        ]
    )
    state, _ = await run(first, db, [HumanMessage("revenue by payment method")])

    second = ScriptedModel(
        script=[
            Plan(action="query", question="Revenue by payment method in May 2024?", chart="bar"),
            SqlDraft(plan="p", sql="SELECT payment_method, sum(total_price) FROM sales_transactions GROUP BY 1"),
            "Same as before.",
        ]
    )
    await run(second, db, [*state["messages"], HumanMessage("only for May")])
    assert "(Assistant's SQL: SELECT payment_method" in second.prompts[0]
    assert "previous question in this conversation was answered with" in second.prompts[1]


async def test_an_empty_database_can_only_reply(make_database: MakeDatabase, sample_db: tuple[str, str]) -> None:
    _, reader = make_database()  # nothing loaded: the reader role exists, the analytics schema does not
    database = Database(reader, max_rows=10, statement_timeout_ms=1000)
    model = ScriptedModel(script=[Plan(action="query", question="q", chart="none"), "Upload a CSV first."])
    try:
        state, _ = await run(model, database, [HumanMessage("how many orders?")])
    finally:
        await database.close()
    assert "No tables yet" in model.prompts[0]
    assert "analysis" not in state["messages"][-1].additional_kwargs
