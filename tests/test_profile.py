from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from csv2sql.ingest.profile import Pii, SqlType, read_table, snake_case


def write(tmp_path: Path, name: str, text: str, encoding: str = "utf-8") -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("customerID", "customer_id"),
        ("dateTime", "date_time"),
        ("HTTPServerName", "http_server_name"),
        ("Order Date", "order_date"),
        ("2nd value", "_2nd_value"),
        ("order", "order_"),
        ("User", "user_"),
        ("  ", "column"),
    ],
)
def test_snake_case(raw: str, expected: str) -> None:
    assert snake_case(raw) == expected


def test_infers_types_from_every_value(tmp_path: Path) -> None:
    table = read_table(
        write(
            tmp_path,
            "t.csv",
            "id,price,flag,day,at,zip,note\n"
            '1,"$1,200.50",Y,2024-05-01,2024-05-01T10:00:00Z,00153,a\n'
            "2,3,N,2024-05-02,2024-05-02T11:30:00Z,94110,\n",
        )
    )
    types = {c.name: c.type for c in table.columns}
    assert types == {
        "id": SqlType.BIGINT,
        "price": SqlType.DOUBLE,
        "flag": SqlType.BOOLEAN,
        "day": SqlType.DATE,
        "at": SqlType.TIMESTAMPTZ,
        "zip": SqlType.TEXT,  # a leading zero means it is a code, not a number
        "note": SqlType.TEXT,
    }
    assert table.rows[0][:5] == (1, 1200.5, True, date(2024, 5, 1), datetime(2024, 5, 1, 10, tzinfo=UTC))
    assert table.rows[1][6] is None


def test_slash_dates_are_day_first_only_when_month_first_is_impossible(tmp_path: Path) -> None:
    us = read_table(write(tmp_path, "us.csv", "d\n05/14/2024\n06/01/2024\n"))
    eu = read_table(write(tmp_path, "eu.csv", "d\n14/05/2024\n06/01/2024\n"))
    assert us.values("d") == [date(2024, 5, 14), date(2024, 6, 1)]
    assert eu.values("d") == [date(2024, 5, 14), date(2024, 1, 6)]


def test_sniffs_delimiter_and_falls_back_to_cp1252(tmp_path: Path) -> None:
    table = read_table(write(tmp_path, "Order Lines.csv", "Name;Group\ncafé;A\nbar;B\n", encoding="cp1252"))
    assert table.name == "order_lines"
    assert [c.name for c in table.columns] == ["name", "group_"]
    assert table.values("name") == ["café", "bar"]


def test_concatenated_exports_with_their_own_header_are_merged(tmp_path: Path) -> None:
    table = read_table(
        write(tmp_path, "s.csv", "supplierID,name,city,approved\n1,A,Paris,Y\nSupplierId,Name\n2,B\n3,C,x\n")
    )
    assert table.values("supplier_id") == [1, 2]
    assert table.values("city") == ["Paris", None]
    assert [(r.line, r.reason) for r in table.rejected] == [(5, "expected 2 fields, found 3")]


def test_detects_personal_data_by_name_and_by_value(tmp_path: Path) -> None:
    table = read_table(
        write(
            tmp_path,
            "p.csv",
            "first_name,contact,payment,city,name\n"
            "Ann,ann@example.com,4111111111111111,Paris,Golden Crumbs\n"
            "Bob,bob@example.org,5500005555555559,Rome,Sugar Rush\n",
        )
    )
    assert {c.name: c.pii for c in table.columns} == {
        "first_name": Pii.PERSON_NAME,
        "contact": Pii.EMAIL,
        "payment": Pii.CARD_NUMBER,
        "city": None,
        "name": None,
    }


def test_low_cardinality_text_lists_its_categories(tmp_path: Path) -> None:
    rows = "\n".join(["visa", "amex", "visa", "amex", "visa"] * 5)
    table = read_table(write(tmp_path, "c.csv", f"method\n{rows}\n"))
    assert table.columns[0].categories == ("amex", "visa")
