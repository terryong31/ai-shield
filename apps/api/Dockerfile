# Build from the repository root: docker build -f apps/api/Dockerfile -t ai-shield-api .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
# Same path in both stages: venv scripts hard-code their interpreter path.
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
COPY packages/engine packages/engine
COPY apps/api apps/api
RUN uv sync --frozen --no-dev --package shield-api --no-editable

FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 10001 shield
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    FEEDBACK_PATH=/app/var/feedback.csv SQLITE_PATH=/app/var/shield.db
RUN mkdir -p /app/var && chown shield /app/var
USER shield
EXPOSE 8000
VOLUME ["/app/var"]
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"]
CMD ["uvicorn", "shield_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
