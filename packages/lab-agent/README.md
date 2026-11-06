# lab-agent

A minimal tool-calling agent over synthetic lab documents, written without an
agent framework or provider SDK. How it works and what it doesn't do:
[`docs/tool-calling-agent.md`](../../docs/tool-calling-agent.md).

- Python 3.10+, no runtime dependencies
- Model: OpenAI Chat Completions (or any OpenAI-compatible server)

## Install

From the repo root, inside a virtual environment:

```bash
pip install -e "packages/lab-agent[dev]"
```

## Run

```bash
export OPENAI_API_KEY=...          # required
export OPENAI_MODEL=gpt-4.1-mini   # optional, any tool-calling chat model
python -m lab_agent --trace "Is my LDL cholesterol above the reference range?"
```

`--trace` prints each tool call and its result to stderr.

## Test, type-check, lint

```bash
cd packages/lab-agent
pytest --cov=lab_agent
mypy src
```

Tests are offline: model responses are scripted, so no API key is needed.
