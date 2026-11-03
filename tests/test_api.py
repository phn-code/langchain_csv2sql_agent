from collections.abc import Iterator
from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict
from starlette.testclient import TestClient

from csv2sql.api import create_app
from csv2sql.settings import Settings

from .conftest import MakeDatabase


def url(conninfo: str) -> str:
    p = conninfo_to_dict(conninfo)
    return f"postgresql://{p['user']}:{p.get('password', '')}@{p['host']}:{p['port']}/{p['dbname']}"


@pytest.fixture
def client(make_database: MakeDatabase, tmp_path: Path) -> Iterator[TestClient]:
    owner, reader = make_database()
    settings = Settings(
        database_url=url(owner),  # type: ignore[arg-type]
        reader_database_url=url(reader),  # type: ignore[arg-type]
        upload_dir=tmp_path / "uploads",
        enrich=False,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def upload(client: TestClient, *files: tuple[str, bytes]):
    return client.post("/datasets", files=[("files", (name, data, "text/csv")) for name, data in files])


def test_upload_query_schema_and_delete(client: TestClient) -> None:
    assert client.get("/datasets").json() == {"report": None}
    assert client.get("/schema").json() == {"tables": []}

    response = upload(client, ("customers.csv", b"customer_id,email\n1,a@x.com\n2,b@x.com\n"))
    assert response.status_code == 200
    assert response.json()["report"]["tables"][0]["withheld"] == [{"column": "email", "pii": "email address"}]

    # A second upload is linked to the first and both stay loaded.
    report = upload(client, ("Orders.csv", b"order_id,customer_id,total\n10,1,5\n11,2,7\n")).json()["report"]
    assert [t["name"] for t in report["tables"]] == ["customers", "orders"]
    assert report["relationships"] == [
        {"table": "orders", "column": "customer_id", "parent_table": "customers", "parent_column": "customer_id",
         "offset": 0, "origin": "name"}
    ]  # fmt: skip

    tables = {t["name"]: t for t in client.get("/schema").json()["tables"]}
    assert [c["name"] for c in tables["customers"]["columns"]] == ["customer_id"]
    assert tables["orders"]["columns"][1]["references"] == "customers(customer_id)"

    assert client.delete("/datasets/customers").json()["report"]["relationships"] == []
    assert [t["name"] for t in client.get("/schema").json()["tables"]] == ["orders"]
    assert client.delete("/datasets/customers").status_code == 404


def test_rejected_uploads_change_nothing(client: TestClient) -> None:
    upload(client, ("a.csv", b"x\n1\n"))
    before = client.get("/schema").json()

    assert upload(client, ("notes.pdf", b"%PDF")).status_code == 400
    assert upload(client, ("empty.csv", b"")).status_code == 400
    assert client.post("/datasets").status_code == 400

    assert client.get("/schema").json() == before
    assert [t["name"] for t in client.get("/datasets").json()["report"]["tables"]] == ["a"]


def test_sample_data_loads(client: TestClient) -> None:
    report = client.post("/datasets/sample").json()["report"]
    assert len(report["tables"]) == 6
    assert len(report["relationships"]) == 5
