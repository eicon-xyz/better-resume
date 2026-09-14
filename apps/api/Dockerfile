ARG UV_IMAGE=ghcr.io/astral-sh/uv:latest
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
COPY README.md ./
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=builder --chown=app:app /app /app
# Ops scripts (fake vendor for the deploy smoke, probes) live next to the app.
COPY --chown=app:app scripts ./scripts
# The process is not root, so the writable state dirs must exist and be owned by it
# (resume uploads + TTS cache). Compose mounts a shared volume here for replicas.
RUN mkdir -p /app/data/resumes /app/data/tts && chown -R app:app /app/data
USER app
EXPOSE 8000
# --proxy-headers: nginx terminates the connection and forwards X-Forwarded-*.
CMD ["uvicorn", "better_resume.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
