from pathlib import Path

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: PostgresDsn | None = Field(default=None, description="Owner connection. Only the ingest job uses it.")
    reader_database_url: PostgresDsn = Field(
        description="Read-only role the agent connects as. Ingest creates this role from the URL."
    )
    model: str = Field(default="openai:gpt-5-mini", description="Any `init_chat_model` identifier.")
    max_rows: int = Field(default=500, description="Rows fetched per query before the result is truncated.")
    statement_timeout_ms: int = 5_000
    max_sql_attempts: int = 3
    enrich: bool = Field(default=True, description="Ask the model to describe uploaded data and suggest keys.")
    upload_dir: Path = Field(
        default=Path("uploads"), description="Upload volume: live files in files/, staged copies beside it."
    )
    max_upload_bytes: int = 50 * 1024 * 1024
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
