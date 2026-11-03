# One image, two processes: the data API (owner credentials) and the agent (read-only credentials).
FROM ghcr.io/astral-sh/uv:0.11-python3.12-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --group server --no-install-project
COPY README.md langgraph.json ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --group server

FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
COPY --chown=app:app data ./data
RUN install -d -o app -g app uploads && touch .env && chown app:app .env
USER app
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 UPLOAD_DIR=/app/uploads
EXPOSE 8000 2024
CMD ["uvicorn", "csv2sql.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
