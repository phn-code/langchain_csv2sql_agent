import pytest

from csv2sql.guard import RejectedQuery, check_query

TABLES = {"sales_transactions", "sales_customers"}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT product, sum(total_price) FROM sales_transactions GROUP BY 1;",
        "WITH x AS (SELECT * FROM sales_customers) SELECT count(*) FROM x",
        "SELECT country FROM sales_customers UNION SELECT 'x'",
        "SELECT date_trunc('month', date_time), count(*) FROM sales_transactions GROUP BY 1",
        "SELECT * FROM generate_series(1, 3)",
    ],
)
def test_allows_read_queries(sql: str) -> None:
    assert check_query(sql, TABLES) == sql.rstrip(";")


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("DROP TABLE sales_customers", "Only SELECT"),
        ("SELECT 1; SELECT 2", "exactly one statement"),
        ("WITH d AS (DELETE FROM sales_customers RETURNING *) SELECT * FROM d", "found DELETE"),
        ("SELECT * INTO copy FROM sales_customers", "found INTO"),
        ("SELECT * FROM sales_customers FOR UPDATE", "found LOCK"),
        ("SELECT * FROM raw.sales_customers", "not `raw.sales_customers`"),
        ("SELECT * FROM information_schema.tables", "not `information_schema.tables`"),
        ("SELECT * FROM pg_roles", "Unknown table `pg_roles`. Available tables: sales_customers, sales_transactions"),
        ("SELECT pg_sleep(10)", "`pg_sleep` is not available"),
        ("SELECT set_config('default_transaction_read_only', 'off', false)", "`set_config` is not available"),
        ("SELECT query_to_xml('select 1', true, true, '')", "`query_to_xml` is not available"),
        ("COPY sales_customers TO '/tmp/x'", "Only SELECT"),
    ],
)
def test_rejects_with_an_actionable_message(sql: str, message: str) -> None:
    with pytest.raises(RejectedQuery, match=message.replace("(", r"\(").replace(".", r"\.")):
        check_query(sql, TABLES)
