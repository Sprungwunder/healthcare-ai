# services/

Deployable web services built on top of the `healthcare_ai` core library.

| Service | What it does |
|---|---|
| [`document-hub/`](document-hub/README.md) | Django 6 service for medical/lab documents: upload, metadata, search, roles, REST API, web UI |

## Conventions

- **One folder per service:** `services/<name>/`. Each is its own project with:
  - its own `pyproject.toml`, Python version and lockfile,
  - a `Dockerfile`,
  - its own `tests/`,
  - an `AGENTS.md` (plus a `CLAUDE.md` containing just `@AGENTS.md`).
- **Depend on core through a local path dependency**, not a shared workspace.
  With pip/setuptools:
  ```toml
  dependencies = [
      "healthcare-ai @ file:../../packages/healthcare-ai-core",
  ]
  ```
  With uv (which rejects relative `file:` URLs), declare it as a source:
  ```toml
  dependencies = ["healthcare-ai"]

  [tool.uv.sources]
  healthcare-ai = { path = "../../packages/healthcare-ai-core", editable = true }
  ```
  Services may need a newer Python than core (Django 6 needs 3.12+, core
  supports 3.10+), so they must not share one dependency resolver range.
- **Services never import each other.** They talk over HTTP/APIs only. Shared
  code goes into core (or a new package under `packages/`).
- **Lint config is shared:** ruff uses the root `pyproject.toml`. If a service
  needs a different `target-version`, add a `[tool.ruff]` section with
  `extend = "../../pyproject.toml"` rather than copying the rules.
- **Tooling:** new services use **uv** with a committed `uv.lock`
  (see `document-hub/`).
- **CI:** add the service's paths to the workflow's `on:` filters and a job in
  `.github/workflows/ci.yml` that runs only when those paths change (see the
  `changes` and `document-hub` jobs).
