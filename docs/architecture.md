# Repository architecture

healthcare-ai is a mono-repo: the shared core library and the web services built
on it live side by side.

```text
packages/healthcare-ai-core/   # the healthcare_ai library (Python 3.10+)
services/<name>/               # deployable services, each its own project
  document-hub/                # Django 6 document service (first service)
configs/ data/ models/ notebooks/   # shared ML workspace
docs/                          # this file and other notes
pyproject.toml                 # shared ruff config only
```

## Why a mono-repo
- **One team, one PR.** Changing core and a service together in one pull request
  is simpler than publishing core and bumping its version across repos.
- **AI assistants stay efficient.** Claude Code and Junie read files only when
  needed, so repo size doesn't cost tokens on its own. A clear layout plus a
  scoped `AGENTS.md` per area keeps the context small, while the assistant can
  still read core when working in a service.

## Key decisions
- **Core is a normal installable package** (`packages/healthcare-ai-core`,
  setuptools, `src/` layout). The import name stays `healthcare_ai`.
- **Services are independent projects**, each with its own `pyproject.toml`,
  Python version, lockfile and Dockerfile. They depend on core through a local
  path dependency rather than a shared workspace, because services may need a
  newer Python than core (e.g. Django 6 needs 3.12+, core supports 3.10+).
- **Services never import each other**; they communicate over HTTP/APIs.
- **Tooling:** core uses pip/setuptools; services use uv with a committed
  `uv.lock` (path dependency on core via `[tool.uv.sources]`). Ruff config is
  shared from the root `pyproject.toml`; mypy and pytest are configured per
  project.
- **CI:** one job per area in `.github/workflows/ci.yml`. The workflow triggers
  on every area's paths; service jobs additionally check their own paths
  (`dorny/paths-filter`) so unrelated changes don't run them.
- **ML workspace stays at the root** (`data/`, `models/`, `notebooks/`,
  `configs/`), shared by all areas and protected by `.gitignore`.

## Document hub (`services/document-hub/`)
Stores medical/lab documents (files + metadata) and will feed a RAG assistant.

- **Layers:** REST API (DRF) and web UI (Django templates) only validate input
  format and call `documents/services.py` (writes, transactional) and
  `documents/search.py` (reads). Shared rules live in `documents/validators.py`,
  so API and UI behave the same.
- **Search** goes through a `DocumentSearchBackend` protocol chosen by
  `DOCUMENT_HUB_SEARCH_BACKEND`; the default queries the database. An
  Elasticsearch backend can be added without touching API or UI.
- **Pipeline hooks:** `document_created/updated/deleted` signals fire after
  commit; `Document.processing_status`, checksum, MIME type and size prepare
  text extraction and indexing.
- **Access:** roles are Django groups (Leser, Redakteur, Administrator) with
  model permissions; files are only served through permission-checked views.

See `services/README.md` for the service conventions and
`docs/document-hub-summary.md` for the decisions behind the document hub.
