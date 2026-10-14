# AGENTS.md: services/

Read the root `AGENTS.md` first for repo-wide rules (PHI, layout).

## What lives here
Deployable web services, one per folder (`services/<name>/`). Currently:
`document-hub/` (Django document service).
Each service has its own `AGENTS.md`; when working on one, read that file and
run commands from that service's directory.

## Rules
- Follow the conventions in `services/README.md` (own pyproject, Python version,
  lockfile, Dockerfile, tests).
- Depend on core via a path dependency on `../../packages/healthcare-ai-core`
  (uv: `[tool.uv.sources]`, see `services/README.md`).
  You may read core code to understand its API; change core only when the task
  requires it, and then also run core's tests.
- Never import another service. Communicate over HTTP/APIs.
- Never log, persist in fixtures or commit real patient data; use synthetic data
  in tests.
