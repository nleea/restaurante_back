# syntax=docker/dockerfile:1

# ---- Stage 1: builder — install deps into a virtualenv with Poetry ----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_NO_INTERACTION=1

# Build deps for asyncpg/argon2 wheels that may need compiling
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app

# Copy only dependency manifests first to leverage layer caching
COPY pyproject.toml poetry.lock ./

# Install runtime deps only (no dev, no project itself yet — src not copied)
RUN poetry install --only main --no-root

# Now copy the source and install the project package
COPY src ./src
COPY README.md ./
RUN poetry install --only main

# ---- Stage 2: runtime — slim image with just the venv + app ----------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Run as a non-root user
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

# Bring the built virtualenv and application code from the builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Migrations + alembic config so the container can run `alembic upgrade head`
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts

USER appuser

EXPOSE 8000

# Default: serve the API. Override the command to run migrations/seeds when needed:
#   docker run ... alembic upgrade head
CMD ["uvicorn", "restaurante.main:app", "--host", "0.0.0.0", "--port", "8000"]
