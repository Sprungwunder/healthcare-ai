# Document Hub: summary

First service in the mono-repo: `services/document-hub/`. It manages medical
and lab-related documents (file plus metadata) with search, roles, a REST API
and a web UI. Later it will be the data source for a RAG assistant. LLM,
embeddings, RAG and Elasticsearch are deliberately not part of this version.

## Architecture decisions

| Topic | Decision | Reason |
|---|---|---|
| Stack | Django 6.0, DRF 3.18, drf-spectacular (with sidecar, no CDN), dj-database-url, psycopg 3, gunicorn, whitenoise | DRF officially supports Django 6, so the Django 5.2 fallback wasn't needed. |
| Python/tooling | ≥ 3.12, uv with `uv.lock` | CI tests 3.12 and 3.14. |
| Core dependency | `[tool.uv.sources] healthcare-ai = { path = "../../packages/healthcare-ai-core" }` | **Deviation from the plan:** uv rejects relative `file:` URLs in `dependencies`. Same effect; the convention in `services/README.md` was extended. |
| Layers | API and UI call only `services.py` (writes) and `search.py` (reads). Rules live in `validators.py`. | API and UI behave the same. The service validates again, so the rules also apply to `seed_demo`. |
| Primary key | UUID | Stable for later syncing with an external index. |
| File check | Extension **and** content, standard library only | Renamed files are rejected (415). |
| Duplicates | SHA-256 unique, 400 with a reference to the existing document | A race condition's `IntegrityError` is turned into the same error. |
| Files and transactions | Validate first, then write the file, then the DB row. On failure the new file is removed. Old files are deleted only after commit. | No orphaned or missing files. |
| Search | `DocumentSearchBackend` protocol, selected via `DOCUMENT_HUB_SEARCH_BACKEND` | An ES backend can be added later without touching API or UI. |
| Pipeline hooks | Signals `document_created/updated/deleted` via `on_commit`, field `processing_status` | Hook for text extraction and indexing. |
| Roles | Groups Reader/Editor/Administrator via data migrations (`sync_role_groups`) | GET additionally requires the `view` permission (`ModelPermissionsWithView`). |
| Auth | Token before session | Unauthenticated API calls get 401 (not 403). |
| Error format | `{"error": {"code", "message", "details"}}` for 400/401/403/404/413/415 | Django `ValidationError`s from the services are translated too. |
| Downloads | Only through permission-checked views, `Cache-Control: private, no-store` | There is no public `MEDIA_URL`. |
| Settings | Everything from env, optional `.env` (small own loader, no extra dependency). `DJANGO_DEBUG` defaults to off; without a secret key nothing starts. | Secure default. **Deviation:** locally you first need `cp .env.example .env`. |
| HTTPS hardening | `DJANGO_HTTPS` (default on, except with DEBUG), HSTS preload opt-in only | compose runs plain HTTP locally and turns the hardening off. |
| Admin | Documents are read-only in the Django admin | Create, edit and delete go through UI/API, so file rules and signals always apply. |
| Runtime generics | `django-stubs-ext` as a runtime dependency (`monkeypatch()`) | For typed views such as `ListView[Document]`. |
| Language | English throughout: code, docs, API docs, CLI, web UI and error messages (`LANGUAGE_CODE = "en-us"`). Content data may be in other languages. | Language rule in the root `AGENTS.md`. The UI was switched from German to English after the first review; migration `0004` renames the existing German role groups and keeps memberships. |

## What changed

Commits on `feature/document-hub` (PR #5):

1. Scaffold: pyproject/uv.lock, settings, agent docs, settings smoke test
2. Models `Document`/`Tag`, migrations incl. role groups, admin
3. Validators, services and signals
4. Search abstraction
5. REST API, permissions, error format, OpenAPI
6. Web UI (templates, responsive CSS, forms, views)
7. `seed_demo`, Dockerfile (+ `Dockerfile.dockerignore`), `compose.yaml`
8. CI job `document-hub` and doc updates (`services/README.md`, `services/AGENTS.md`, root `AGENTS.md`/`README.md`, `docs/architecture.md`)
9. This summary; docs switched to English and the language rule added to `AGENTS.md`
10. Web UI, messages and role names switched to English (migrations `0003`, `0004`)

CI: the `on:` filters now include `services/document-hub/**`. A `changes` job
(`dorny/paths-filter`) makes sure `document-hub` runs only when the hub, core,
the ruff config or the workflow file change. The job runs on Python 3.12 and
3.14: `uv sync --locked`, ruff, mypy, pytest against a Postgres 17 service
container, then `docker build` (3.14 only). The `core` job is unchanged. It now
also runs when only the hub changes, because workflow-level filters trigger all
jobs.

## Test results (2026-10-14)

- `uv run pytest --cov`: **153 tests passing, coverage 97.7 %** (threshold 90 %). Same result on Python 3.12 and 3.14.
- Same suite against Postgres 17 (compose `db`): passing.
- `uv run mypy .` (django-stubs, djangorestframework-stubs): no errors.
- `ruff check .` / `ruff format --check .` from the repo root: clean.
- Core: `pytest --cov=healthcare_ai` (100 %) and `mypy src` passing.
- `drf-spectacular --validate --fail-on-warn`: schema without warnings.
- **GitHub Actions (PR #5):** all jobs green: `changes`, `core` (3.10, 3.11, 3.12, 3.14), `document-hub` (3.12, 3.14) incl. Postgres tests and Docker build.
- `docker compose up --build`, then manually with `curl`:
  - Permissions: anonymous 401, reader can't create (403), editor can't delete (403), admin deletes (204).
  - Upload, tag search, PATCH and download work.
  - Duplicate 400, forged PDF 415, 10.5 MB file 413.
  - Web flow via session: login, upload, search, edit (editor), delete (admin). Buttons appear according to the role.
  - `/media/` returns 404.

Not verified: rendering in a real browser (desktop and phone layout).

## Known limitations

- SQLite folds only ASCII in `icontains` (`Ä` ≠ `ä`). Postgres handles this correctly.
- Uploads that are too large are rejected only after they've been received. In production the proxy should limit the request size (e.g. `client_max_body_size`).
- Anyone with `auth.change_user` can also set `is_superuser` in the Django admin (Django's default behaviour). The Administrator role is therefore effectively fully trusted.
- Migrations run on container start. With several replicas they belong in a separate job.
- Tags are returned alphabetically, not in input order.

## Next steps

1. Optional: ask uploaders to confirm that a document contains no patient data.
2. Text extraction (PDF/DOCX) as a signal receiver using `processing_status`, then embeddings and an index.
3. `ElasticsearchSearchBackend` with full-text search once title search is no longer enough.
4. Virus scanning, object storage (S3 via django-storages), audit log.
5. Administrator role without superuser escalation (custom `UserAdmin`).
