# AGENTS.md: packages/lab-agent

Read the root `AGENTS.md` first for repo-wide rules (PHI, layout).

## What lives here
`lab_agent`: a minimal, framework-free tool-calling agent over synthetic lab
documents. It is a training exercise, explained in `docs/tool-calling-agent.md`.
It doesn't depend on `healthcare_ai`, and nothing depends on it.

## Commands (run from this directory)
- Tests: `pytest --cov=lab_agent`
- Types: `mypy src`
- Lint/format (from the repo root): `ruff check . && ruff format --check .`

## Conventions
- Python 3.10+, strict typing, standard library only. No agent framework and
  no provider SDK; the OpenAI API is called with `urllib`.
- Keep layers separate: `tools.py` and `documents.py` don't import any model
  code; `agent.py` only uses the `ModelClient` protocol; provider JSON lives
  only in `openai_client.py`.
- Tests never touch the network: fake the `ModelClient` or patch `urlopen`.
- Documents are fictional (`SYN-` patient references). Never add real data.
