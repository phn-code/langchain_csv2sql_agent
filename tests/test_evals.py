from csv2sql.database import QueryResult
from csv2sql.evals import CASES, load_cases, results_match


def result(*rows: list[object]) -> QueryResult:
    width = len(rows[0]) if rows else 0
    return {
        "columns": [{"name": f"c{i}", "kind": "text"} for i in range(width)],
        "rows": [list(r) for r in rows],  # type: ignore[misc]
        "truncated": False,
        "elapsed_ms": 0,
    }


def test_columns_match_by_content_and_extras_are_allowed() -> None:
    expected = result(["a", 1.0], ["b", 2.0])
    assert results_match(expected, result([2, "b", "x"], [1, "a", "y"]), ordered=False)
    assert not results_match(expected, result([2, "a"], [1, "b"]), ordered=False)  # rows must stay aligned


def test_order_matters_only_when_asked() -> None:
    expected = result(["a", 1], ["b", 2])
    flipped = result(["b", 2], ["a", 1])
    assert results_match(expected, flipped, ordered=False)
    assert not results_match(expected, flipped, ordered=True)


def test_values_are_normalized() -> None:
    assert results_match(result([6.654]), result([6.65]), ordered=False)
    assert results_match(result(["2024-05-01"]), result(["2024-05-01T00:00:00+00:00"]), ordered=False)
    assert not results_match(result([1]), result([1], [1]), ordered=False)


def test_bundled_cases_parse() -> None:
    cases = load_cases(CASES)
    assert len({c.id for c in cases}) == len(cases) >= 20
    assert any(len(c.turns) > 1 for c in cases)
