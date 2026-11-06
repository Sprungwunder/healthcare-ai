# lab-agent

A minimal tool-calling agent over synthetic lab documents with structured state
management and SQLite persistence, written without an agent framework or provider
SDK. Details and architecture notes:
- [`docs/tool-calling-agent.md`](../../docs/tool-calling-agent.md)
- [`docs/agent-memory-and-state.md`](../../docs/agent-memory-and-state.md)

- Python 3.10+, standard library only (no external agent framework)
- Model: OpenAI Chat Completions (or any OpenAI-compatible server), or Claude
  via the Anthropic Messages API
- State & memory: explicit `AgentState`, step tracking, and `SQLiteStateStore`

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

With Claude instead:

```bash
export ANTHROPIC_API_KEY=...            # required
export ANTHROPIC_MODEL=claude-opus-5-5  # optional, the default
python -m lab_agent --provider anthropic --trace "Is my LDL cholesterol above the reference range?"
```

### Persistence and Task Resumption

```bash
# Run with SQLite state checkpointing
python -m lab_agent --db agent_state.db --task-id task-101 "Analyze thyroid panel"

# List persisted tasks
python -m lab_agent --db agent_state.db --list-tasks

# View structured agent state
python -m lab_agent --db agent_state.db --task-id task-101 --show-state

# Resume an interrupted task
python -m lab_agent --db agent_state.db --task-id task-101 --resume
```

## Test, type-check, lint

```bash
cd packages/lab-agent
pytest --cov=lab_agent
mypy src
```

Tests are offline: model responses are scripted, so no API key is needed.
