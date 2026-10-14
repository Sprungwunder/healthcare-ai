# Build from the repository root (core is a path dependency):
#   docker build -f services/document-hub/Dockerfile .
# Excludes: services/document-hub/Dockerfile.dockerignore

# --- build: resolve the locked dependencies into /opt/venv -----------------
FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src/services/document-hub
COPY packages/healthcare-ai-core /src/packages/healthcare-ai-core
COPY services/document-hub/pyproject.toml services/document-hub/uv.lock ./
# --no-editable installs core into the venv, so /src isn't needed at runtime.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

COPY services/document-hub/ ./
RUN DJANGO_SECRET_KEY=collectstatic-only /opt/venv/bin/python manage.py \
    collectstatic --noinput

# --- runtime ---------------------------------------------------------------
FROM python:3.14-slim
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEDIA_ROOT=/data/media \
    STATIC_ROOT=/app/staticfiles

RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app \
    && mkdir -p /data/media && chown app:app /data/media

COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY --from=build /src/services/document-hub/ ./

USER app
VOLUME ["/data/media"]
EXPOSE 8000

# Migrations run on start (single instance). With several replicas, run
# `manage.py migrate` as a separate one-off job instead.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn document_hub.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3} --timeout 60"]
