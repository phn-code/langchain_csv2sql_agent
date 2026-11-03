# csv2sql

Upload CSV files and ask questions about them in plain English. csv2sql loads the files into Postgres as typed tables with real primary and foreign keys. It then answers each question by writing SQL, running it under a read-only role, and showing you the answer, the rows, a chart, and the SQL it ran.

The sample data in `data/` is a bakery franchise business: transactions, customers, franchises, suppliers, and reviews. It is messy in ways real exports are messy, and the loader handles each problem:

- `sales_suppliers.csv` is two exports joined end to end. The second export has its own shorter header. The loader maps it onto the first header by name, so all 48 suppliers load and `sales_franchises.supplier_id` becomes a foreign key.
- Customer ids in `sales_transactions.csv` are offset from `sales_customers.csv` by exactly 1,000,000. The loader detects the shift and corrects it in the `analytics` schema. The source rows in `raw` keep their original values.
- Every customer id is also a valid transaction id. A loader that matched on values alone would link the two tables. csv2sql requires a name match before it checks values, so it does not.

## Run it with Docker

1. Put a model key in `.env`:

	```sh
	echo "OPENAI_API_KEY=sk-..." > .env
	```

	To use Anthropic instead, set `ANTHROPIC_API_KEY` and `MODEL=anthropic:claude-sonnet-5-5`.

2. Start the stack:

	```sh
	docker compose up --build
	```

3. Open <http://localhost:3000>. Click **Load sample data**, or drop your own CSV files on the page.

| Service    | Port | Credentials        | Job                                                   |
| ---------- | ---- | ------------------ | ----------------------------------------------------- |
| `web`      | 3000 | none               | The chat, schema explorer, and upload UI              |
| `data-api` | 8000 | Postgres owner     | Accepts uploads, rebuilds the database, serves schema |
| `agent`    | 2024 | read-only role     | The LangGraph agent that answers questions            |
| `db`       | none | none               | Postgres 16                                           |

## Develop locally

You need [uv](https://docs.astral.sh/uv/), Docker, Node 22 or later, and pnpm.

```sh
uv sync
docker run -d --name csv2sql_pg -e POSTGRES_USER=owner -e POSTGRES_PASSWORD=owner \
	-e POSTGRES_DB=csv2sql -p 5436:5432 postgres:16
cp .env.example .env                     # then add OPENAI_API_KEY
uv run csv2sql-ingest data               # load the sample and print what was inferred
uv run uvicorn csv2sql.api:create_app --factory --port 8000
uv run langgraph dev                     # agent on http://localhost:2024
cd web && pnpm install && pnpm dev       # UI on http://localhost:5173
```

`csv2sql-ingest DIR --dry-run --no-ai` prints the inferred types, keys, and withheld columns without a database or a model.

## Check your changes

```sh
uv run ruff check && uv run ruff format --check
uv run pyright                           # strict mode
uv run pytest                            # starts a throwaway Postgres with testcontainers
```

Set `TEST_DATABASE_URL` to an owner URL to reuse a running Postgres instead of starting a container.

The tests use a scripted model, so they need no API key. They check the security boundary directly against Postgres: the reader role cannot read `raw`, cannot write even after it turns off read-only mode, and cannot run a query past the statement timeout.

## Measure answer quality

`evals/cases.toml` holds 21 questions about the sample data, including three follow-up conversations. Each case has a reference query. A case passes when the agent's result contains the same rows as the reference result. Column names, column order, and extra columns do not matter, and row order matters only for cases marked `ordered`.

```sh
uv run csv2sql-ingest data
uv run csv2sql-eval --model openai:gpt-5-mini
uv run csv2sql-eval --model openai:gpt-5-nano --only top_product follow_up_pronoun
```

The command prints each case, the pass rate, and how many cases passed only after the agent corrected its own SQL. It writes the full results to `evals/results/`.

## Configuration

Settings come from environment variables or `.env`.

| Variable               | Default              | Used by          | Meaning                                                      |
| ---------------------- | -------------------- | ---------------- | ------------------------------------------------------------ |
| `DATABASE_URL`         | none                 | data API, ingest | Owner connection. Required to load data.                     |
| `READER_DATABASE_URL`  | none                 | all              | Read-only role. The data API creates the role from this URL. |
| `MODEL`                | `openai:gpt-5-mini`  | all              | Any [`init_chat_model`] identifier.                          |
| `ENRICH`               | `true`               | data API, ingest | Ask the model for descriptions and missed relationships.     |
| `MAX_ROWS`             | `500`                | agent            | Rows fetched per query before the result is truncated.       |
| `STATEMENT_TIMEOUT_MS` | `5000`               | agent, reader    | Postgres cancels queries that run longer.                    |
| `MAX_SQL_ATTEMPTS`     | `3`                  | agent            | Attempts at a working query before the agent gives up.       |
| `UPLOAD_DIR`           | `data`               | data API         | Where uploaded files are kept.                               |
| `MAX_UPLOAD_BYTES`     | `52428800`           | data API         | Largest accepted file.                                       |
| `CORS_ORIGINS`         | localhost 5173, 3000 | data API         | JSON list of origins allowed to call the data API.           |

[`init_chat_model`]: https://python.langchain.com/api_reference/langchain/chat_models/langchain.chat_models.base.init_chat_model.html

## Layout

```text
src/csv2sql/
├── ingest/
│   ├── profile.py    # read one file: encoding, delimiter, header sections, types, PII
│   ├── keys.py       # primary and foreign keys: names propose, values prove
│   ├── enrich.py     # optional AI descriptions and relationship suggestions, verified against the data
│   ├── load.py       # raw and analytics schemas, constraints, comments, reader role
│   └── pipeline.py   # directory in, report out
├── api.py            # data API: upload, delete, schema
├── database.py       # catalog from pg_catalog; read-only, bounded queries
├── guard.py          # rejects non-SELECT SQL with a message the model can act on
├── charts.py         # result shape to Vega-Lite spec, no generated code
├── agent/graph.py    # plan -> write_sql <-> run_sql -> respond
├── evals.py          # execution-accuracy harness
└── server.py         # graph entry point for langgraph.json
web/                  # React UI
```

[docs/architecture.md](docs/architecture.md) explains why the system is built this way.
