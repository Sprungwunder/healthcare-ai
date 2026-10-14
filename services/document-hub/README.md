# Healthcare Document Hub

Django service for medical and lab-related documents: lab protocols, SOPs,
guidelines and technical manuals. It stores the file plus metadata, offers
search, role-based access, a REST API and a German web UI. Later it will be the
data source for a RAG assistant; this version has no LLM, embedding or
search-engine code yet.

> Only upload documents **without patient data** (see the PHI rules in the root
> `AGENTS.md`). Demo and test data are synthetic.

## Quick start (local, SQLite)

```bash
cd services/document-hub
cp .env.example .env          # DJANGO_DEBUG=true is set there for local use
uv sync
uv run python manage.py migrate
uv run python manage.py seed_demo --password '<choose-one>'   # optional
uv run python manage.py runserver
```

Open <http://localhost:8000/>. `seed_demo` creates six synthetic documents and,
if a password is given, the users `demo-leser`, `demo-redakteur` and
`demo-admin`. Without a `.env` the settings refuse to start unless
`DJANGO_SECRET_KEY` is set, because `DJANGO_DEBUG` defaults to off.
Create a real admin account with `uv run python manage.py createsuperuser`.

## Docker (Postgres)

```bash
cp .env.example .env   # set DJANGO_SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build
docker compose exec web python manage.py seed_demo   # uses DOCUMENT_HUB_DEMO_PASSWORD
```

The image is built from the repository root (core is a path dependency),
runs as a non-root user with gunicorn and applies migrations on start.
Uploads live in the `media` volume, the database in `pgdata`. compose serves
plain HTTP on `127.0.0.1:8000` and therefore sets `DJANGO_HTTPS=false`; in
production keep HTTPS on and run behind a TLS proxy.

## Roles

| Role (group) | Can |
|---|---|
| Leser | view, search and download documents, read the API docs |
| Redakteur | + create and edit all documents (incl. replacing the file) |
| Administrator | + delete documents; manage users in `/admin/` (needs `is_staff`) |

Users without a role can log in but see nothing (403). Assign roles in the
Django admin (`/admin/` → Users → Groups).

## Documents and rules

- Fields: title, type (`lab_protocol`, `sop`, `guideline`, `technical_manual`),
  source (+ optional URL), publication date (optional, not in the future),
  language (`de`, `en`), up to 20 free tags (trimmed, lowercased, 1–50 chars),
  and one file.
- Files: PDF, DOCX, TXT or MD, at most `DOCUMENT_HUB_MAX_UPLOAD_SIZE` bytes
  (default 10 MB). The content must match the extension (`%PDF-` header, DOCX
  ZIP with `word/document.xml`, UTF-8 text), so renamed files are rejected.
  Identical files (same SHA-256) are rejected with a reference to the existing
  document.
- Stored as `MEDIA_ROOT/documents/<yyyy>/<mm>/<uuid>.<ext>`; downloads go
  through a permission-checked view (no public media URL).
- Deleting is permanent and removes the file. Replacing the file resets
  `processing_status` to `pending`.

## REST API

Base path `/api/v1/`. Interactive docs at `/api/docs/` (OpenAPI schema at
`/api/schema/`), both for logged-in readers.

| Method | Path | Role |
|---|---|---|
| GET | `/documents/?q=&document_type=&tags=a,b&language=&ordering=&page=` | Leser |
| POST | `/documents/` (multipart, with `file`) | Redakteur |
| GET | `/documents/{id}/` | Leser |
| PATCH / PUT | `/documents/{id}/` (multipart or JSON; `file` optional) | Redakteur |
| DELETE | `/documents/{id}/` | Administrator |
| GET | `/documents/{id}/download/` | Leser |
| GET | `/tags/?q=` | Leser |
| POST | `/auth/token/` (`username`, `password`) | – |

Search: `q` matches the title (contains, case-insensitive), `tags` requires
*all* given tags, filters are combined with AND. `ordering` is one of
`-created_at` (default), `created_at`, `title`, `-title`, `published_on`,
`-published_on`. Pages hold 20 results.

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/token/ \
  -d username=demo-redakteur -d password='<password>' | jq -r .token)
curl -H "Authorization: Token $TOKEN" \
  -F title="SOP Probenannahme" -F document_type=sop -F source="Labor" \
  -F language=de -F tags="präanalytik, routine" -F file=@sop.pdf \
  localhost:8000/api/v1/documents/
curl -H "Authorization: Token $TOKEN" "localhost:8000/api/v1/documents/?tags=routine"
```

Errors always look like this:

```json
{"error": {"code": "validation_error", "message": "Die Eingabe ist ungültig.",
           "details": {"title": ["Dieses Feld darf nicht leer sein."]}}}
```

| Status | `code` |
|---|---|
| 400 | `validation_error` (field errors in `details`, incl. duplicate files) |
| 401 | `not_authenticated`, `authentication_failed` |
| 403 | `permission_denied` |
| 404 | `not_found` |
| 413 | `file_too_large` |
| 415 | `unsupported_file_type` (file), `unsupported_media_type` (request body) |

## Configuration

All settings come from environment variables (or `.env`); see `.env.example`.

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | – | required unless `DJANGO_DEBUG` is on |
| `DJANGO_DEBUG` | `false` | development mode |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | comma-separated |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | – | e.g. behind a proxy |
| `DJANGO_HTTPS` | on unless DEBUG | SSL redirect, secure cookies, HSTS |
| `DJANGO_SECURE_HSTS_SECONDS` / `_PRELOAD` | `3600` / `false` | HSTS tuning |
| `DJANGO_TRUST_X_FORWARDED_PROTO` | `false` | only behind a proxy that sets it |
| `DATABASE_URL` | SQLite `db.sqlite3` | e.g. `postgres://user:pw@host/db` |
| `MEDIA_ROOT` | `./media` | upload directory |
| `DOCUMENT_HUB_MAX_UPLOAD_SIZE` | `10485760` | bytes |
| `DOCUMENT_HUB_SEARCH_BACKEND` | `documents.search.DatabaseSearchBackend` | dotted path |
| `LOG_LEVEL` | `INFO` | root log level |

## Extension points

- **Search engine:** implement `documents.search.DocumentSearchBackend`
  (`search(SearchQuery) -> QuerySet[Document]`) and point
  `DOCUMENT_HUB_SEARCH_BACKEND` at it.
- **Processing / indexing:** connect to `document_created`, `document_updated`
  (`file_replaced=True/False`) and `document_deleted` in `documents.signals`.
  They fire after the transaction commits. Track progress in
  `Document.processing_status`.

## Development

```bash
uv run pytest --cov        # fails below 90 % coverage
uv run mypy .
uv run ruff check . && uv run ruff format --check .
# Against Postgres (e.g. the compose db, host port POSTGRES_HOST_PORT):
DATABASE_URL=postgres://document_hub:<pw>@127.0.0.1:5432/document_hub uv run pytest
```

Note: on SQLite, case-insensitive title search only folds ASCII letters
(`Ä`/`ä` differ); Postgres handles umlauts.
