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

RUN uv sync --no-dev --no-editable --frozen

RUN uv run python -m compileall -q -j 0 .venv/
