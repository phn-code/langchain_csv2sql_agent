import os
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from csv2sql.ingest.pipeline import ingest

SAMPLE = Path(__file__).resolve().parents[1] / "data"
READER_PASSWORD = "reader-test-password"


@pytest.fixture(scope="session")
def server_url() -> Iterator[str]:
    """Owner URL for a throwaway Postgres: TEST_DATABASE_URL if set, otherwise a testcontainer."""
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16", driver=None) as pg:
        yield pg.get_connection_url()


type MakeDatabase = Callable[[], tuple[str, str]]


@pytest.fixture(scope="session")
def make_database(server_url: str) -> MakeDatabase:
    """Create an empty database; return (owner_url, reader_url)."""

    def make() -> tuple[str, str]:
        name = f"t_{uuid.uuid4().hex[:12]}"
        with psycopg.connect(server_url, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{name}"')  # type: ignore[arg-type]
        owner = make_conninfo(server_url, dbname=name)
        params = conninfo_to_dict(owner)
        reader = make_conninfo(owner, user=f"reader_{params['user']}", password=READER_PASSWORD)
        return owner, reader

    return make


@pytest.fixture(scope="session")
def sample_db(make_database: MakeDatabase) -> tuple[str, str]:
    owner, reader = make_database()
    with psycopg.connect(owner) as conn:
        ingest(SAMPLE, conn, reader_url=reader, statement_timeout_ms=2000)
    return owner, reader
