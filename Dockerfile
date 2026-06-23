FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
WORKDIR /app

ARG APP_VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${APP_VERSION}

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project --frozen

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY LICENSE ./LICENSE
COPY README.md ./README.md

# TODO: make a lightweight version later without examples / tests, but for now keep things together for demo
COPY examples/ ./examples/
COPY tests/ ./tests/

RUN uv sync --no-dev --no-editable --frozen

RUN uv run python -m compileall -q -j 0 .venv/
