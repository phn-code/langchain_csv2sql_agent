from csv2sql.charts import build_chart
from csv2sql.database import QueryResult


def result(columns: list[tuple[str, str]], rows: list[list[object]]) -> QueryResult:
    return {
        "columns": [{"name": n, "kind": k} for n, k in columns],  # type: ignore[typeddict-item]
        "rows": rows,  # type: ignore[typeddict-item]
        "truncated": False,
        "elapsed_ms": 1,
    }


def test_auto_picks_a_line_for_time_and_keeps_series() -> None:
    spec = build_chart(
        "auto",
        result(
            [("day", "temporal"), ("product", "text"), ("revenue", "number")],
            [["2024-05-01", "a", 1], ["2024-05-02", "a", 2]],
        ),
        "Revenue",
    )
    assert spec is not None
    assert spec["mark"]["type"] == "line"
    assert spec["encoding"]["x"] == {"field": "day", "type": "temporal"}
    assert spec["encoding"]["color"] == {"field": "product", "type": "nominal"}
    assert spec["data"]["values"][1] == {"day": "2024-05-02", "product": "a", "revenue": 2}


def test_bar_keeps_the_sql_order_and_arc_uses_theta() -> None:
    data = result([("product", "text"), ("revenue", "number")], [["b", 9], ["a", 1]])
    bar = build_chart("auto", data, "t")
    pie = build_chart("arc", data, "t")
    assert bar
    assert bar["mark"]["type"] == "bar"
    assert bar["encoding"]["x"]["sort"] is None
    assert pie
    assert pie["encoding"]["theta"]["field"] == "revenue"
    assert pie["encoding"]["color"]["field"] == "product"


def test_no_chart_without_a_numeric_value_or_enough_rows() -> None:
    assert build_chart("bar", result([("a", "text"), ("b", "text")], [["x", "y"], ["z", "w"]]), "t") is None
    assert build_chart("bar", result([("a", "text"), ("n", "number")], [["x", 1]]), "t") is None
    assert build_chart("none", result([("a", "text"), ("n", "number")], [["x", 1], ["y", 2]]), "t") is None
