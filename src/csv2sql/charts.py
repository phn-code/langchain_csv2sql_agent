"""Compile a query result into a Vega-Lite spec. No generated code runs; the result's shape decides.

Columns are read positionally: the first is the x axis (or the slice label for `arc`), the last numeric column is
the value, and an optional text column between them splits the data into series.
"""

from typing import Any, Literal

from csv2sql.database import QueryResult, ResultColumn

type ChartKind = Literal["none", "auto", "bar", "line", "area", "point", "arc"]

_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"
_AUTO: dict[str, ChartKind] = {"temporal": "line", "number": "point", "text": "bar"}
_TYPES = {"number": "quantitative", "temporal": "temporal", "text": "nominal"}


def _field(column: ResultColumn, **extra: Any) -> dict[str, Any]:
    return {"field": column["name"], "type": _TYPES[column["kind"]], **extra}


def build_chart(kind: ChartKind, result: QueryResult, title: str) -> dict[str, Any] | None:
    columns = result["columns"]
    if kind == "none" or len(columns) < 2 or len(result["rows"]) < 2:
        return None
    x, rest = columns[0], columns[1:]
    values = [c for c in rest if c["kind"] == "number"]
    if not values:
        return None
    y = values[-1]
    series = next((c for c in rest if c["kind"] == "text" and c is not y), None)

    if kind == "auto":
        kind = _AUTO[x["kind"]]

    data = [{c["name"]: v for c, v in zip(columns, row, strict=True)} for row in result["rows"]]
    encoding: dict[str, Any]
    if kind == "arc":
        encoding = {"theta": _field(y, stack=True), "color": _field(x, sort=None)}
    else:
        x_extra: dict[str, Any] = {"sort": None} if x["kind"] == "text" else {}
        encoding = {"x": _field(x, **x_extra), "y": _field(y)}
        if series:
            encoding["color"] = _field(series)
    encoding["tooltip"] = [_field(c) for c in columns]

    mark: dict[str, Any] = {"type": kind, "tooltip": True}
    if kind in ("line", "area"):
        mark["point"] = len(data) <= 60
    return {
        "$schema": _SCHEMA,
        "title": title,
        "width": "container",
        "data": {"values": data},
        "mark": mark,
        "encoding": encoding,
    }
