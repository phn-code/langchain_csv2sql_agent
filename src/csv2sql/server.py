"""Entry point for `langgraph dev` / `langgraph up` (see langgraph.json)."""

from langchain.chat_models import init_chat_model

from csv2sql.agent.graph import build_graph
from csv2sql.database import Database
from csv2sql.settings import Settings

settings = Settings()  # type: ignore[call-arg]
graph = build_graph(
    init_chat_model(settings.model),
    Database(
        str(settings.reader_database_url),
        max_rows=settings.max_rows,
        statement_timeout_ms=settings.statement_timeout_ms,
    ),
    max_attempts=settings.max_sql_attempts,
)
