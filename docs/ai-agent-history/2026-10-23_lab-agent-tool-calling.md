# Task: Minimal tool-calling agent over synthetic lab documents

- **Date / time**: 2026-10-23 20:53
- **Status**: Completed / successful (PR #7 open, not merged; live API run
  pending account credits)

## 1. Task Overview
Training exercise on LLM tool calling and agent loops. Build, without an agent
framework, a minimal agent that answers questions about synthetic lab
documents through two independent tools: `search_lab_documents(query)` (title
and description search) and `get_document_details(document_id)`. The loop
passes tool definitions to an LLM, processes structured tool calls, validates
tool names and arguments, executes the Python function, returns the result
and repeats until a final answer. It limits iterations and handles unknown
tools, invalid arguments, missing documents and model/API errors. Tools stay
separate from the LLM integration, tests mock the model (no network or
credentials), and a short English doc explains the loop and its limitations.

## 2. Steps Taken
1. Inspected the repo: no LLM provider, SDK or API key configuration existed.
   Core (`healthcare_ai`) rules out I/O-to-services code and new runtime
   dependencies; the Django document hub would add unrelated parts.
2. Proposed a plan: a new stdlib-only package `packages/lab-agent`, layered
   tools / registry / model protocol / loop / provider client. Asked for the
   provider; the user chose OpenAI and approved the plan.
3. Created branch `feature/lab-agent` and the package skeleton (setuptools,
   `src/` layout, pytest and mypy config mirroring core).
4. TDD, one cycle per layer, each test file failing first: tools, registry
   and argument validation, agent loop (scripted fake client), OpenAI client
   (patched `urlopen`), CLI.
5. Ran ruff (fixer reformatted two lines), fixed one mypy error in a test,
   and verified on Python 3.14 (project venv) and 3.10 (throwaway venv in
   `/tmp`).
6. Wrote `docs/tool-calling-agent.md`, package README/AGENTS/CLAUDE, updated
   root `AGENTS.md`, `docs/architecture.md`, `.env.example` and CI.
7. Attempted one live run with the user's `packages/lab-agent/src/.env`
   (gitignored, values never printed): the API answered HTTP 429, no credits.
8. Committed, pushed and opened PR #7 against `main`.

## 3. File Changes
- `packages/lab-agent/pyproject.toml`: package `lab-agent`, no runtime deps,
  dev deps as in core, pytest/mypy config.
- `packages/lab-agent/src/lab_agent/documents.py`: `LabDocument`, `LabResult`
  and six fictional lab reports (`SYN-` patient refs).
- `packages/lab-agent/src/lab_agent/tools.py`: the two tools, `ToolError`,
  `InvalidQueryError`, `DocumentNotFoundError`.
- `packages/lab-agent/src/lab_agent/registry.py`: `Tool` dataclass,
  `LAB_TOOLS`, `validate_arguments`, `InvalidArgumentsError`.
- `packages/lab-agent/src/lab_agent/model.py`: neutral message types,
  `ToolCall`, `ModelClient` protocol, `ModelError`.
- `packages/lab-agent/src/lab_agent/agent.py`: `run_agent`,
  `execute_tool_call`, `AgentResult`, `MaxIterationsExceededError`, system
  prompt.
- `packages/lab-agent/src/lab_agent/openai_client.py`: `OpenAIChatClient`
  (Chat Completions over `urllib`), `build_request_body`, `parse_response`.
- `packages/lab-agent/src/lab_agent/__main__.py`: CLI with `--trace` and
  `--max-iterations`.
- `packages/lab-agent/tests/`: `test_tools.py`, `test_registry.py`,
  `test_agent.py`, `test_openai_client.py`, `test_cli.py`.
- `packages/lab-agent/{README,AGENTS,CLAUDE}.md`: package docs.
- `docs/tool-calling-agent.md`: loop, example exchange, error policy,
  limitations.
- `AGENTS.md`, `docs/architecture.md`: repo map and architecture entries.
- `.env.example`: commented `OPENAI_API_KEY`, `OPENAI_MODEL`,
  `OPENAI_BASE_URL`.
- `.github/workflows/ci.yml`: `lab-agent` job (Python 3.10, 3.14) behind a
  paths filter.
- `docs/ai-agent-history/2026-10-23_lab-agent-tool-calling.md`: this log.

## 4. Verification & Testing
- `pytest --cov=lab_agent` (in `packages/lab-agent`): 58 passed, 99 %
  coverage, fully offline.
- `mypy src` (and `mypy src tests`): no issues on 3.14; `mypy src` and
  `pytest` also clean on Python 3.10.
- `ruff check .` and `ruff format --check .` (repo root): clean.
- Core tests (`packages/healthcare-ai-core`): still pass.
- CI YAML parsed successfully; job list and filter outputs checked.
- Live OpenAI run: request reached the API, HTTP 429 (no credits). The error
  path produced a clean `ModelError` without the key; a successful end-to-end
  answer has not been observed yet.

## 5. Key Decisions & Notes
- **Separate package, not core or document hub:** core forbids external I/O
  and runtime deps; the document hub would tie the exercise to Django and a DB.
- **No SDK, no framework:** `urllib` + `json` keep the raw tool-calling
  request and response visible, which is the learning goal.
- **Layering:** tools know nothing about LLMs; the loop depends only on the
  `ModelClient` protocol; OpenAI JSON lives only in `openai_client.py`. Tests
  substitute a scripted client.
- **Error policy:** errors the model can fix (unknown tool, bad JSON or
  arguments, missing document) are returned as tool results and the loop
  continues; unfixable ones (API/network, malformed response, empty answer,
  iteration limit) raise. Unexpected tool exceptions propagate as bugs.
- **Double validation:** `strict: true` is sent to OpenAI, but arguments are
  still validated locally because model output is untrusted and compatible
  servers may ignore the flag.
- **Hand-written validator** for the small schema subset instead of the
  `jsonschema` dependency.
- **Default model** `gpt-4.1-mini` is an assumption; override via
  `OPENAI_MODEL`.
- **Follow-ups:** the agent does not load `.env` files itself; the user's
  `.env` sits in `packages/lab-agent/src/` rather than the repo root expected
  by `.env.example`. `--trace` only prints after a successful run. Rerun the
  live test once the OpenAI account has credits.
