# healthcare-ai-core

The shared Python library of the healthcare-ai mono-repo, imported as `healthcare_ai`.
It holds reusable, framework-free building blocks (for example validation and
normalization of medical measurements in `healthcare_ai.measurements`) that ML
pipelines, notebooks and the web services under `services/` build on.

- Python 3.10+
- No runtime dependencies (standard library only, so far)

## Install

From the repo root, inside a virtual environment:

```bash
pip install -e "packages/healthcare-ai-core[dev]"
```

## Test, type-check, lint

```bash
cd packages/healthcare-ai-core
pytest --cov=healthcare_ai
mypy src
```

Ruff is configured once for the whole repo, so run it from the repo root:

```bash
ruff check . && ruff format --check .
```
