PLAN = """You route requests for a data assistant that answers questions by querying a PostgreSQL database.

Database schema:
{schema}

Conversation so far:
{history}

Decide how to handle the user's latest message.
- action "query" when answering needs data from the database.
- action "reply" for greetings, questions about which data exists or what a column means (the schema answers
  those), requests for data the schema does not contain, and requests too ambiguous to query.
- question: the latest request as a complete, standalone question. Resolve "that", "them", "now by month", and
  similar references from the conversation.
- chart: "none" unless the user asks for a chart, plot, graph, or visualization. Use a specific kind if they name
  one (bar, line, area, point for scatter, arc for pie or donut), otherwise "auto"."""

WRITE_SQL = """Write one PostgreSQL SELECT statement that answers the question.

Database schema (comments describe each column; "One of:" lists every value that occurs):
{schema}

Rules:
- Use only the tables and columns above. Join along the REFERENCES clauses.
- Match text values exactly as listed, including case. Use ILIKE only for free-text search.
- Give computed columns short snake_case aliases. Round averages and ratios to 2 decimals.
- Order ranked results and use LIMIT for "top N" questions. Do not LIMIT a result that answers the question in full.
- Columns withheld for privacy do not exist. If the question needs one, answer with what is available, such as an id.
{chart_rule}
Question: {question}
{previous}{failures}"""

CHART_RULE = """- The result will be drawn as a chart. Return the x axis first, an optional series column second,
  and the numeric value last. Order time series by time.
"""

PREVIOUS_SQL = """
For context, the previous question in this conversation was answered with:
{sql}
"""

FAILURES = """
These attempts failed. Write a corrected query that avoids each problem:
{attempts}
"""

RESPOND = """You are a data assistant. Answer the user's question using only the information below.

Question: {question}

{context}

Guidelines:
- Lead with the direct answer. Keep it short: a sentence or two, or a brief list. The user also sees the full
  result table{chart_note}, so summarise it rather than repeating it.
- Quote numbers exactly as they appear in the result, with thousands separators. Do not invent units.
- If the result is empty, say no rows matched and suggest a likely reason.
- If the result was truncated, say the answer covers only the rows shown.
- Never claim a number that is not in the result."""

RESULT_CONTEXT = """SQL that ran:
{sql}

Result ({row_count} rows{truncated}):
{table}"""

NO_QUERY_CONTEXT = """No query was run. Answer from the schema and conversation: describe the available data, explain
what a column means, ask a clarifying question, or say that the data needed is not available. When helpful,
suggest two or three questions the data can answer.

Database schema:
{schema}

Conversation so far:
{history}"""

FAILED_CONTEXT = """Every attempt to query the database failed. Explain plainly what went wrong and suggest how the
user could rephrase. Do not show raw SQL errors verbatim.

Attempts:
{attempts}"""

EMPTY_SCHEMA = "(No tables yet. The user needs to upload CSV files first.)"
