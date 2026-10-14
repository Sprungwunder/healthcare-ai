# AGENTS.md: services/document-hub

Read the root `AGENTS.md` (PHI rules) and `services/AGENTS.md` first.

## What lives here
Django 6 service that stores medical/lab documents (files + metadata) with a
REST API (`/api/v1/`) and a server-rendered German web UI. It is the future
data source for a RAG assistant; there is no LLM/embedding/search-engine code yet.

- `document_hub/`: project (settings from env, URLs, WSGI/ASGI).
  `settings_test.py` is used by pytest and mypy.
- `documents/`: the app.
  - `models.py` (Document, Tag, enums), `validators.py` (shared rules: file
    size/type, tags, dates), `services.py` (create/update/delete, transactional),
    `search.py` (`SearchQuery`, pluggable `DocumentSearchBackend`),
    `signals.py` (sent after commit), `permissions.py` (roles -> groups).
  - `api/` (DRF) and `web/` (forms + views) are thin: they validate input format
    and call `services.py` / `search.py` only. Keep business rules out of them.
- `tests/`: pytest-django, synthetic data only.

## Commands (run from this directory, uv is at `~/.local/bin/uv`)
- Install: `uv sync`
- Tests: `uv run pytest --cov` (fails under 90 % coverage)
- Types: `uv run mypy .`
- Lint/format: from the repo root, `ruff check . && ruff format --check .`
  (or `uv run ruff ...` from here).
- Run: `uv run python manage.py migrate && uv run python manage.py runserver`
- Demo data: `uv run python manage.py seed_demo [--password ...]`

## Conventions
- Python 3.12+ (CI: 3.12 and 3.14). Strict typing like core.
- Dependencies via `uv add`; commit `uv.lock`. CI runs `uv sync --locked`.
- Roles are Django groups (`documents/permissions.py`); changing a role's
  permissions needs a new data migration calling `sync_role_groups`.
- Never log request data or file contents. Uploaded files are only served
  through permission-checked download views (no public `MEDIA_URL`).
- UI strings are German; code, comments and API field names are English.
- Tests: keep `MEDIA_ROOT` on the tmp dir (autouse fixture in `tests/conftest.py`).
