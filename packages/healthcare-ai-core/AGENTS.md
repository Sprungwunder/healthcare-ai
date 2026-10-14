# AGENTS.md: packages/healthcare-ai-core

Read the root `AGENTS.md` first for repo-wide rules (PHI, layout).

## What lives here
The `healthcare_ai` library (`src/healthcare_ai/`) and its tests (`tests/`).
Services and notebooks depend on it, so treat its public API (what
`healthcare_ai/__init__.py` exports) as a contract: changing it means checking
callers in `services/` in the same change.

## Commands (run from this directory)
- Tests: `pytest --cov=healthcare_ai`
- Types: `mypy src`
- Lint/format (from the repo root): `ruff check . && ruff format --check .`

## Conventions
- Python 3.10+ syntax only; CI runs 3.10, 3.11, 3.12 and 3.14.
- Strict typing: every function is annotated (`disallow_untyped_defs`).
- Standard library first. Adding a runtime dependency is a deliberate decision;
  it ships to every service.
- No web framework, database or I/O-to-services code here. That belongs in a
  service under `services/`.
- Fail fast with typed exceptions on invalid clinical data (see `measurements.py`).
- New public names are re-exported in `healthcare_ai/__init__.py` and covered by
  tests in `tests/`.
