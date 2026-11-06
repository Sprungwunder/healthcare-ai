# Task: Claude (Anthropic Messages API) provider for the lab agent

- **Date / time**: 2026-11-06 10:33
- **Status**: Completed / successful (stacked PR on `feature/lab-agent`;
  live run with Claude succeeded, see `packages/lab-agent/src/lab_agent/examples.md`)

## 1. Task Overview
The lab agent from PR #7 could only use `OpenAIChatClient`, and the user's
OpenAI account could not be funded, so the agent had never answered a
question end to end. Goal: add the Claude API as a second provider so the
feature can be tested, without changing the tools or the agent loop.

## 2. Steps Taken
1. Read the lab-agent package: the loop depends only on the `ModelClient`
   protocol, provider JSON lives in one module, and the package rules are
   standard library only, no provider SDK.
2. Looked up the Messages API request and response format (endpoint,
   headers, `tool_use` / `tool_result` blocks, `is_error`, stop reasons,
   error JSON, current model and API version).
3. Added `AnthropicMessagesClient` over `urllib`, mirroring
   `openai_client.py`, and an opaque `provider_data` field on
   `AssistantMessage` so Claude's thinking blocks can be replayed unchanged.
4. Added `--provider {openai,anthropic}` to the CLI (default `openai`).
5. Wrote offline tests (patched `urlopen`). They found a bug in the first
   version (content blocks were reordered when no `fallback` block was
   present), which was fixed.
6. Updated the package README and AGENTS.md, `docs/tool-calling-agent.md`,
   `docs/architecture.md` and `.env.example`.
7. The user ran the agent live with `--provider anthropic --trace`; the
   output is recorded in `examples.md`.

## 3. File Changes
- `packages/lab-agent/src/lab_agent/anthropic_client.py` (new):
  `AnthropicMessagesClient`, `build_request_body`, `parse_response`.
- `packages/lab-agent/src/lab_agent/model.py`: `AssistantMessage.provider_data`
  (excluded from equality and `repr`).
- `packages/lab-agent/src/lab_agent/__main__.py`: `--provider` option.
- `packages/lab-agent/src/lab_agent/examples.md` (new): live example run.
- `packages/lab-agent/tests/test_anthropic_client.py` (new), `tests/test_cli.py`.
- `packages/lab-agent/{README,AGENTS}.md`, `docs/tool-calling-agent.md`
  (provider comparison table), `docs/architecture.md`, `.env.example`.
- `docs/ai-agent-history/2026-11-06_lab-agent-claude-provider.md`: this log.

## 4. Verification & Testing
- `pytest --cov=lab_agent` (in `packages/lab-agent`): 83 passed, 99 %
  coverage, fully offline.
- `mypy src`: no issues. `ruff check .` and `ruff format --check .` (repo
  root): clean.
- Live run (user, `claude-opus-5-5`): the model searched, fetched `LAB-1002`
  and answered correctly (LDL 3.7 mmol/L vs. reference < 3.0), citing the
  document ID and giving no diagnosis.

## 5. Key Decisions & Notes
- **`urllib`, not the `anthropic` SDK:** the package rules forbid provider
  SDKs, and the raw JSON is the learning goal.
- **Thinking blocks replayed via `provider_data`:** the current Claude models
  always think and require thinking blocks to be sent back unchanged in a
  tool loop; the neutral types stay provider-free, the loop is unchanged.
- **Tool results grouped:** all `tool_result` blocks of one turn go into one
  `user` message, with the real `is_error` flag.
- **Refusal and truncation raise `ModelError`** instead of looking like an
  empty answer.
- **Server-side fallback on by default** (`fallbacks: "default"`, beta
  `server-side-fallback-2026-07-01`): a request declined by a safety
  classifier is retried on another model in the same call. Only text before
  the last `fallback` block is replayed. Can be turned off with
  `server_side_fallback=False`.
- **Defaults:** model `claude-opus-5-5`, API version `2026-10-21`,
  `max_tokens` 16000, effort `medium` (set explicitly), timeout 120 s.
- **Follow-ups:** this PR is stacked on PR #7 and should be merged after it.
  No retries on 429/529. `examples.md` sits in the package source folder.
