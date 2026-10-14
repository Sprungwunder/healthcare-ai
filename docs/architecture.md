# Repository architecture

healthcare-ai is a mono-repo: the shared core library and the web services built
on it live side by side.

```text
packages/healthcare-ai-core/   # the healthcare_ai library (Python 3.10+)
services/<name>/               # deployable services, each its own project
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
- **Tooling:** pip/setuptools for now. Ruff config is shared from the root
  `pyproject.toml`; mypy and pytest are configured per project.
- **CI:** one job per area in `.github/workflows/ci.yml`, each with a `paths:`
  filter so unrelated changes don't trigger it.
- **ML workspace stays at the root** (`data/`, `models/`, `notebooks/`,
  `configs/`), shared by all areas and protected by `.gitignore`.

See `services/README.md` for the service conventions.
