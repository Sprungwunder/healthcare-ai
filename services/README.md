# services/

Deployable web services built on top of the `healthcare_ai` core library.
There are none yet; the first planned one is a Django "document hub". The
conventions below are a starting point and will be revisited when that service
is designed.

## Conventions

- **One folder per service:** `services/<name>/`. Each is its own project with:
  - its own `pyproject.toml`, Python version and lockfile,
  - a `Dockerfile`,
  - its own `tests/`,
  - an `AGENTS.md` (plus a `CLAUDE.md` containing just `@AGENTS.md`).
- **Depend on core through a local path dependency**, not a shared workspace:
  ```toml
  dependencies = [
      "healthcare-ai @ file:../../packages/healthcare-ai-core",
  ]
  ```
  Services may need a newer Python than core (Django 6 needs 3.12+, core
  supports 3.10+), so they must not share one dependency resolver range.
- **Services never import each other.** They talk over HTTP/APIs only. Shared
  code goes into core (or a new package under `packages/`).
- **Lint config is shared:** ruff uses the root `pyproject.toml`. If a service
  needs a different `target-version`, add a `[tool.ruff]` section with
  `extend = "../../pyproject.toml"` rather than copying the rules.
- **CI:** add a job in `.github/workflows/ci.yml` with a `paths:` filter on
  `services/<name>/**`, mirroring the `core` job.
