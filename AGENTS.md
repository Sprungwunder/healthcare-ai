# AGENTS.md

Guidance for AI coding assistants (Claude Code, Junie, ...) working in this repo.
`CLAUDE.md` and `.junie/guidelines.md` only point here.

## Repo map
- `packages/healthcare-ai-core/`: the `healthcare_ai` Python library (3.10+). See its `AGENTS.md`.
- `packages/lab-agent/`: minimal tool-calling agent (training exercise, stdlib only). See its `AGENTS.md`.
- `services/`: deployable web services, one folder each. See `services/AGENTS.md`.
  - `services/document-hub/`: Django document service. See its `AGENTS.md`.
- `configs/`, `data/`, `models/`, `notebooks/`: shared ML workspace. `data/` and `models/` contents are gitignored.
- `docs/`: architecture notes (`docs/architecture.md`) and write-ups.
- `pyproject.toml` (root): shared ruff config only, not a package.

## How to work here
- Work inside one area at a time and read that area's `AGENTS.md` before editing.
- Run area commands from the area's directory; run ruff from the repo root.
- Read other areas only when needed (e.g. a service reading core's API).

## Project language: English
- Everything written into the repo or to GitHub is in English, **even when the
  conversation with the user is in another language** (e.g. German): code,
  identifiers, comments, docstrings, Markdown and other docs, API docs
  (OpenAPI descriptions), CLI help and output, commit messages, PR titles and
  descriptions.
- This includes user-facing product text (web UI, validation and API error
  messages) and synthetic demo and test data. Only real content data may be in other
  languages (e.g. an uploaded German document and its title).

## Commands
Setup (repo root, in a venv): `pip install -e "packages/healthcare-ai-core[dev]"`
(and `pip install -e "packages/lab-agent[dev]"` for the lab agent).
Services use uv instead (`~/.local/bin/uv` if not on PATH); see each service's `AGENTS.md`.

| Area | Directory | Commands |
|------|-----------|----------|
| Lint/format (all) | repo root | `ruff check .` and `ruff format --check .` |
| Core | `packages/healthcare-ai-core` | `pytest --cov=healthcare_ai`, `mypy src` |
| Lab agent | `packages/lab-agent` | `pytest --cov=lab_agent`, `mypy src` |
| Document hub | `services/document-hub` | `uv sync`, `uv run pytest --cov`, `uv run mypy .` |

## Healthcare data rules (non-negotiable)
- Never commit patient data, PHI/PII or credentials. Never print or log them.
- Data placed in `data/raw/` must be de-identified (HIPAA, GDPR).
- Secrets go in `.env` (template: `.env.example`), never in code.
- Don't add medical imaging files (DICOM, NIfTI) or model weights to git; `.gitignore` blocks them, don't override it.
- Tests use synthetic data only.
