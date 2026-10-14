# AGENTS.md

Guidance for AI coding assistants (Claude Code, Junie, ...) working in this repo.
`CLAUDE.md` and `.junie/guidelines.md` only point here.

## Repo map
- `packages/healthcare-ai-core/`: the `healthcare_ai` Python library (3.10+). See its `AGENTS.md`.
- `services/`: deployable web services, one folder each (none yet). See `services/AGENTS.md`.
- `configs/`, `data/`, `models/`, `notebooks/`: shared ML workspace. `data/` and `models/` contents are gitignored.
- `docs/`: architecture notes (`docs/architecture.md`) and write-ups.
- `pyproject.toml` (root): shared ruff config only, not a package.

## How to work here
- Work inside one area at a time and read that area's `AGENTS.md` before editing.
- Run area commands from the area's directory; run ruff from the repo root.
- Read other areas only when needed (e.g. a service reading core's API).

## Commands
Setup (repo root, in a venv): `pip install -e "packages/healthcare-ai-core[dev]"`

| Area | Directory | Commands |
|------|-----------|----------|
| Lint/format (all) | repo root | `ruff check .` and `ruff format --check .` |
| Core | `packages/healthcare-ai-core` | `pytest --cov=healthcare_ai`, `mypy src` |

## Healthcare data rules (non-negotiable)
- Never commit patient data, PHI/PII or credentials. Never print or log them.
- Data placed in `data/raw/` must be de-identified (HIPAA, GDPR).
- Secrets go in `.env` (template: `.env.example`), never in code.
- Don't add medical imaging files (DICOM, NIfTI) or model weights to git; `.gitignore` blocks them, don't override it.
- Tests use synthetic data only.
