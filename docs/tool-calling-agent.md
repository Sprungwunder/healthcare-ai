# Tool-calling lab document agent

`packages/lab-agent` is a minimal agent loop built for learning: an LLM answers
questions about synthetic lab documents by calling two Python functions. It
has no agent framework and no provider SDK, so every step is visible in plain,
standard-library Python.

## The pieces

| Module | Role | Knows about the LLM? |
|--------|------|----------------------|
| `documents.py` | Six fictional lab reports (`SYN-` patient refs) | no |
| `tools.py` | `search_lab_documents(query)`, `get_document_details(document_id)` | no |
| `registry.py` | `Tool` = function + name, description, JSON Schema; argument validation | no (schema only) |
| `model.py` | Neutral message types and the `ModelClient` protocol | interface only |
| `agent.py` | The loop | via the protocol |
| `openai_client.py` | Neutral types to and from Chat Completions JSON over `urllib` | yes, OpenAI only |

The model never runs code. It only *asks* for a tool by name with JSON
arguments; our code decides whether and how to run it.

## The loop

```text
messages = [system prompt, user request]
repeat up to max_iterations times:
    reply = model(messages, tool definitions)
    append reply
    if reply has no tool calls:
        return reply.content                  # final answer
    for each tool call in reply:
        look up tool by name                  # unknown -> error result
        parse arguments as JSON object        # malformed -> error result
        validate against schema               # mismatch -> error result
        run the Python function               # ToolError -> error result
        append tool result (JSON, linked by tool_call_id)
raise MaxIterationsExceededError
```

One exchange for "What was the TSH value?", as the model sees it:

```text
user       What was the TSH value?
assistant  tool_call c1: search_lab_documents({"query": "TSH"})
tool c1    [{"document_id": "LAB-1004", "title": "Thyroid function", ...}]
assistant  tool_call c2: get_document_details({"document_id": "LAB-1004"})
tool c2    {"document_id": "LAB-1004", "results": [{"analyte": "TSH", "value": 5.9, ...}]}
assistant  TSH was 5.9 mU/L (reference 0.4-4.0) in LAB-1004.
```

That is three model calls (iterations) and two tool executions. The API is
stateless, so the whole conversation is sent again every time.

## Error handling

The question is always: *can the model fix this?*

- **Yes:** unknown tool, invalid JSON, wrong or missing arguments, empty
  query, unknown document ID. The error goes back as a tool result
  (`{"error": "..."}`, `is_error=True`) and the loop continues, so the model
  can retry, for example by searching first and then using a real ID.
- **No:** HTTP, network or timeout failures, a malformed API response, or an
  empty answer raise `ModelError`. Running out of iterations raises
  `MaxIterationsExceededError`. Unexpected exceptions inside a tool are bugs
  and propagate unchanged, so stack traces never reach the model.

Arguments are validated in our code even though `strict: true` asks OpenAI to
follow the schema: model output is untrusted input, and OpenAI-compatible
servers may ignore the flag.

## Limitations

- **Not for clinical use.** The data is synthetic and the model may still
  misread values or hallucinate. The system prompt forbids inventing data and
  giving diagnoses, but a prompt is not a guarantee.
- **Naive search:** case-insensitive substring match per word, so there are no
  synonyms ("sugar" won't find HbA1c) and no semantic ranking. That would be a
  job for the document hub's search backend or embeddings.
- **No retries, streaming or rate-limit handling.** One failed API call ends
  the run.
- **Growing context:** every iteration resends the full history, so cost and
  latency grow with each tool call. There is no truncation or summarization.
- **Iteration limit is a blunt guard:** it stops loops but also stops long
  legitimate tasks, and `--trace` only prints after a successful run.
- **Tiny schema validator:** it supports string properties, required keys and
  no extra keys, which is all these tools need. Richer schemas would need more
  code or the `jsonschema` package.
- **Single provider:** only an OpenAI client exists. Another provider means one
  new `ModelClient` implementation; tools and loop stay unchanged.
- **Data leaves the machine:** with the real API, tool results are sent to
  OpenAI. That is fine for synthetic data but not for PHI unless covered by an
  appropriate agreement (or use a local OpenAI-compatible server via
  `OPENAI_BASE_URL`).
