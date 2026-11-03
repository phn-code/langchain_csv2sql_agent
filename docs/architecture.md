# About the csv2sql design

This page explains the decisions behind csv2sql. Each section names a problem and the choice that solves it. For setup and commands, see the [README](../README.md).

## Postgres enforces the security boundary, not a parser

The agent runs SQL that a model wrote, so the model's SQL must not be able to change data or read personal data. A keyword blocklist cannot promise that. The previous version blocked `DROP`, `DELETE`, and four other words. `COPY`, `GRANT`, `SELECT INTO`, `pg_sleep`, and data-modifying CTEs all got past it, and the agent connected as a superuser.

csv2sql gives the agent a role that cannot do harm, whatever SQL it runs:

- The role has `SELECT` on the `analytics` schema and no other privilege. It cannot read `raw`, create tables, or create temp tables.
- Every query runs inside `SET TRANSACTION READ ONLY` with `SET LOCAL statement_timeout`.
- Every query runs as a named cursor. Postgres accepts `DECLARE CURSOR` only for a single `SELECT` or `VALUES`, so a second statement or a `DELETE` fails to parse.
- Columns flagged as personal data are not in `analytics` at all. A query cannot leak a column that does not exist.

`tests/test_database.py` sends hostile SQL straight to the database, past the guard, and checks that Postgres refuses each statement.

`guard.py` still exists because Postgres errors are poor feedback for a model. "Unknown table `customers`. Available tables: ..." gets a better second attempt than "relation does not exist". The guard is there for accuracy, not safety.

## Personal data is left out, not redacted after the fact

The previous version asked a second LLM call to redact names and emails from each answer. That cost a model call per answer and was a best effort at most. csv2sql classifies columns at load time by name, and by value for email addresses and Luhn-valid card numbers. It then leaves those columns out of `analytics`. Each table comment lists what was withheld, so the agent can tell the user that it cannot see email addresses instead of guessing. Sample values of withheld columns are never sent to a model, including during enrichment.

## Names propose keys, values prove them, and Postgres checks the proof

Key inference has two failure modes, and the sample data contains both. Name rules miss keys when the naming is unconventional. Value rules invent keys when ranges overlap by accident: every customer id in the sample is also a transaction id.

csv2sql accepts a foreign key only when a name rule or the model proposes it and every child value appears in the parent key. A constant shift is allowed, which recovers the customer ids that are offset by 1,000,000. The loader then adds each key as a real `FOREIGN KEY` constraint, so Postgres validates the inference a second time. A wrong key fails the load instead of producing wrong joins.

The previous loader fixed the shift with an `UPDATE` on the only copy of the data. csv2sql keeps the source values in `raw` and applies the shift when it builds `analytics`. The column comment records the shift.

## The schema lives in Postgres

Profiles, descriptions, and keys are stored as `COMMENT ON` text and constraints. The agent reads them from `pg_catalog` at the start of every turn and renders them as DDL, the format models have seen most. No separate metadata table can drift from the real schema, and a new upload is visible on the next question without a restart.

## One transaction per load, one directory as the source

Every upload or delete rebuilds both schemas from all files in the upload directory, inside one transaction that holds an advisory lock. Keys are re-inferred across every file each time, so a new `orders.csv` links to an existing `customers.csv`. If a file fails to load, the transaction rolls back and the staged directory is discarded, so the previous data and the previous files both stay. A rebuild is slower than an incremental change, but it is always consistent and easy to reason about. That trade is right for files people upload by hand.

## A fixed graph instead of an open agent loop

Answering a data question takes the same few steps every time: understand the question, write SQL, run it, and answer. csv2sql encodes those steps as a LangGraph graph with one loop, from a failed query back to `write_sql`, bounded by `MAX_SQL_ATTEMPTS`. A tool-calling agent, or a deep agent with planning and sub-agents, would decide the steps at run time. That costs tokens on every question, makes failures harder to reproduce, and makes evals noisier. It would pay off for open-ended investigations that need many queries. The evals show whether users need that.

The `plan` step rewrites each follow-up as a standalone question and sees the previous turn's SQL. That is how "now only for visa" works.

## Charts come from the result's shape

The previous version charted by running model-written Python in the server process, which also held the database password. csv2sql never runs generated code. The model picks only a chart kind. `write_sql` is told to return the x axis first, an optional series column, and the value last. `charts.py` turns that shape into a Vega-Lite spec. The UI renders the spec, so charts are interactive and themed, and they cannot execute anything.

## Only the answer streams

The `plan` and `write_sql` calls carry LangGraph's `nostream` tag, so their JSON never reaches the chat. Each node emits a custom progress event instead, which the UI shows as steps, including each failed attempt. `tests/test_agent.py` fails if any node other than `respond` streams a message.
