"""Data API: upload and delete CSV files, read the schema the agent sees.

This is the only process with owner credentials. Every change is staged: the upload directory is copied, the change
is applied to the copy, and the copy is ingested. Files replace the live directory only after the database
transaction commits, so a bad file leaves both the data and the directory as they were.
"""

import asyncio
import json
import shutil
import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from csv2sql.database import Database
from csv2sql.ingest.load import prepare
from csv2sql.ingest.pipeline import SUFFIXES, Report, enrichment_model, ingest
from csv2sql.settings import Settings

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data"
REPORT_FILE = ".report.json"


class DataService:
    def __init__(self, settings: Settings, sample_dir: Path = SAMPLE_DIR):
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required for the data API")
        self.settings = settings
        self.sample_dir = sample_dir
        self.directory = settings.upload_dir
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = Database(
            str(settings.reader_database_url),
            max_rows=settings.max_rows,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
        self._lock = asyncio.Lock()

    def prepare(self) -> None:
        with psycopg.connect(str(self.settings.database_url)) as conn:
            prepare(conn, str(self.settings.reader_database_url), self.settings.statement_timeout_ms)

    def report(self) -> Report | None:
        path = self.directory / REPORT_FILE
        return json.loads(path.read_text()) if path.exists() else None

    def _ingest(self, directory: Path) -> Report:
        with psycopg.connect(str(self.settings.database_url)) as conn:
            return ingest(
                directory,
                conn,
                reader_url=str(self.settings.reader_database_url),
                statement_timeout_ms=self.settings.statement_timeout_ms,
                model=enrichment_model(self.settings),
            )

    def _apply(self, change: Callable[[Path], None]) -> Report:
        staging = self.directory.parent / f".staging-{uuid.uuid4().hex}"
        shutil.copytree(self.directory, staging)
        try:
            change(staging)
            report = self._ingest(staging)
            (staging / REPORT_FILE).write_text(json.dumps(report))
            live = {p.name for p in self.directory.iterdir()}
            staged = {p.name for p in staging.iterdir()}
            for name in staged:
                (staging / name).replace(self.directory / name)
            for name in live - staged:
                (self.directory / name).unlink()
            return report
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    async def apply(self, change: Callable[[Path], None]) -> Report:
        async with self._lock:
            return await run_in_threadpool(self._apply, change)


def _error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def schema(request: Request) -> JSONResponse:
    service: DataService = request.app.state.service
    catalog = await service.database.catalog()
    return JSONResponse(
        {
            "tables": [
                {
                    "name": t.name,
                    "comment": t.comment,
                    "columns": [
                        {
                            "name": c.name,
                            "type": c.type,
                            "comment": c.comment,
                            "primary_key": c.primary_key,
                            "references": c.references,
                        }
                        for c in t.columns
                    ],
                }
                for t in catalog.tables
            ]
        }
    )


async def datasets(request: Request) -> JSONResponse:
    service: DataService = request.app.state.service
    return JSONResponse({"report": service.report()})


async def upload(request: Request) -> JSONResponse:
    service: DataService = request.app.state.service
    limit = service.settings.max_upload_bytes
    async with request.form(max_files=50, max_part_size=limit) as form:
        files = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
        if not files:
            return _error("Attach one or more files in the `files` field.")
        contents: dict[str, bytes] = {}
        for file in files:
            name = Path(file.filename or "").name
            if Path(name).suffix.lower() not in SUFFIXES or name.startswith("."):
                return _error(f"{name or 'File'}: only {', '.join(SUFFIXES)} files are accepted.")
            data = await file.read()
            if len(data) > limit:
                return _error(f"{name} is larger than {limit // 1024 // 1024} MB.", 413)
            contents[name] = data

    def add(directory: Path) -> None:
        for name, data in contents.items():
            (directory / name).write_bytes(data)

    try:
        report = await service.apply(add)
    except (ValueError, UnicodeError, psycopg.Error) as error:
        return _error(f"Could not load the files: {error}")
    return JSONResponse({"report": report})


async def load_sample(request: Request) -> JSONResponse:
    service: DataService = request.app.state.service

    def add(directory: Path) -> None:
        for path in service.sample_dir.glob("*.csv"):
            shutil.copy(path, directory / path.name)

    return JSONResponse({"report": await service.apply(add)})


async def delete(request: Request) -> JSONResponse:
    service: DataService = request.app.state.service
    table = request.path_params["table"]
    report = service.report()
    source = next((t["source"] for t in (report or {"tables": []})["tables"] if t["name"] == table), None)
    if source is None:
        return _error(f"No table named {table}.", 404)
    return JSONResponse({"report": await service.apply(lambda d: (d / source).unlink())})


async def healthz(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings()  # type: ignore[call-arg]
    service = DataService(settings)

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncGenerator[None]:
        await run_in_threadpool(service.prepare)
        app.state.service = service
        yield
        await service.database.close()

    return Starlette(
        routes=[
            Route("/schema", schema),
            Route("/datasets", datasets),
            Route("/datasets", upload, methods=["POST"]),
            Route("/datasets/sample", load_sample, methods=["POST"]),
            Route("/datasets/{table}", delete, methods=["DELETE"]),
            Route("/healthz", healthz),
        ],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=settings.cors_origins,
                allow_methods=["GET", "POST", "DELETE"],
                allow_headers=["*"],
            )
        ],
        lifespan=lifespan,
    )
