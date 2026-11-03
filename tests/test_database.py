import psycopg
import pytest

from csv2sql.database import Database, QueryError


@pytest.fixture
async def db(sample_db: tuple[str, str]):
    database = Database(sample_db[1], max_rows=100, statement_timeout_ms=500)
    yield database
    await database.close()


def test_sample_loads_every_row(sample_db: tuple[str, str]) -> None:
    with psycopg.connect(sample_db[0]) as conn:
        counts = dict(
            conn.execute(
                "SELECT relname, (xpath('/row/n/text()', query_to_xml("
                "format('SELECT count(*) AS n FROM analytics.%I', relname), false, true, '')))[1]::text::int "
                "FROM pg_class WHERE relnamespace = 'analytics'::regnamespace AND relkind = 'r'"
            ).fetchall()
        )
    assert counts == {
        "media_customer_reviews": 204,
        "media_gold_reviews_chunked": 196,
        "sales_customers": 300,
        "sales_franchises": 48,
        "sales_suppliers": 48,
        "sales_transactions": 3333,
    }


async def test_catalog_renders_keys_comments_and_hides_personal_data(db: Database) -> None:
    rendered = (await db.catalog()).render()
    assert "customer_id bigint REFERENCES sales_customers(customer_id)" in rendered
    assert "transaction_id bigint PRIMARY KEY" in rendered
    assert "One of: 'amex', 'mastercard', 'visa'." in rendered
    assert "Withheld for privacy: first_name (person name)" in rendered
    defined = {line.split()[0] for line in rendered.splitlines() if line.startswith("  ")}
    assert defined.isdisjoint({"first_name", "last_name", "email_address", "phone_number", "address", "card_number"})


async def test_shifted_key_joins_every_transaction(db: Database) -> None:
    result = await db.query("SELECT count(*) FROM sales_transactions JOIN sales_customers USING (customer_id)")
    assert result["rows"] == [[3333]]


@pytest.mark.parametrize(
    ("statement", "error"),
    [
        ("SELECT * FROM raw.sales_customers", "permission denied for schema raw"),
        ("SELECT email_address FROM sales_customers", 'column "email_address" does not exist'),
        # Queries run as DECLARE CURSOR, which only parses a single SELECT or VALUES.
        ("DELETE FROM sales_transactions", 'syntax error at or near "DELETE"'),
        ("SELECT pg_sleep(2)", "canceling statement due to statement timeout"),
        ("SELECT 1; SELECT 2", "cannot insert multiple commands"),
    ],
)
async def test_the_database_is_the_boundary(db: Database, statement: str, error: str) -> None:
    """These bypass the guard on purpose: the reader role must refuse them on its own."""
    with pytest.raises(QueryError, match=error):
        await db.query(statement)


def test_reader_cannot_write_even_after_disabling_read_only(sample_db: tuple[str, str]) -> None:
    with psycopg.connect(sample_db[1], autocommit=True) as conn:
        conn.execute("SET default_transaction_read_only = off")
        for statement in ("DELETE FROM sales_transactions", "CREATE TEMP TABLE t (a int)", "CREATE TABLE t (a int)"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)  # type: ignore[arg-type]


async def test_results_are_capped_and_json_safe(db: Database) -> None:
    result = await db.query("SELECT transaction_id, date_time, unit_price::numeric FROM sales_transactions")
    assert len(result["rows"]) == 100
    assert result["truncated"]
    assert [c["kind"] for c in result["columns"]] == ["number", "temporal", "number"]
    assert isinstance(result["rows"][0][1], str)
    assert isinstance(result["rows"][0][2], float)
