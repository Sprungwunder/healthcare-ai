# Agent Memory, State Management, and Task Resumption

This document explains the architecture, persistence mechanism, and task resumption
model implemented in `packages/lab-agent`.

---

## 1. Core Concepts: Memory, State, and History

To build reliable multi-step agents, three concepts must be kept distinct:

```text
+---------------------------------------------------------------------------------+
|                                PERSISTENT MEMORY                                |
|  Durability layer (SQLite/DB) storing checkpoints, agent state, and history.   |
+---------------------------------------------------------------------------------+
       |                                                            |
       v (restores)                                                 v (restores)
+-----------------------------------+             +-------------------------------+
|       CONVERSATION HISTORY        |             |          AGENT STATE          |
| Linear model transcript:          |             | Explicit domain data & status:|
| - System prompt                   |             | - task_id & lifecycle status  |
| - User request                    |             | - document_id                 |
| - Assistant tool calls & turns    |             | - extracted_values            |
| - Tool return messages            |             | - completed & pending steps   |
| Purpose: Context window for LLM   |             | - intermediate_results        |
+-----------------------------------+             +-------------------------------+
```

### Conversation History vs. Agent State vs. Persistent Memory

| Concept | What it contains | Primary Consumer | Mutation Lifecycle |
|---|---|---|---|
| **Conversation History** | Ordered sequence of `Message` instances (`SystemMessage`, `UserMessage`, `AssistantMessage`, `ToolMessage`). | The LLM (via `ModelClient.complete`). | Appended sequentially turn by turn. |
| **Agent State** | Explicit, structured dictionary / dataclass (`AgentState`) containing task ID, lifecycle status, document reference, extracted analyte values, step completion tracker, and intermediate outputs. | The application orchestrator, business rules, UI, and checkpoints. | Updated deterministically on tool completion and status transitions. |
| **Persistent Memory** | External SQLite database or storage backend (`StateStore`) storing serialized state and conversation history. | Application instances across restarts and crashes. | Persisted atomically after each turn or step. |

---

## 2. Multi-Step Healthcare Document Analysis Process

The agent executes a four-step structured document analysis process:

```text
[1. Search Document] --> [2. Extract Values] --> [3. Evaluate Values] --> [4. Generate Summary]
```

1. **Search Document (`search_lab_documents`)**:
   Searches synthetic laboratory documents for relevant titles or analytes (e.g., `"lipid"`, `"thyroid"`, `"cbc"`). The match result is stored in `state.intermediate_results["search_results"]` and marks `"search_document"` as completed.

2. **Extract Values (`get_document_details`)**:
   Retrieves full document metadata and analyte measurement records (`analyte`, `value`, `unit`, `reference_range`). Updates `state.document_id`, populates `state.extracted_values`, and marks `"extract_values"` as completed.

3. **Evaluate Values (`evaluate_lab_results`)**:
   Deterministic evaluation of extracted analyte values against reference ranges (`"< 5.2"`, `"> 1.0"`, `"0.4-4.0"`). Classifies findings into `normal`, `high`, or `low`, calculates abnormal counts, stores findings in `state.intermediate_results["evaluation"]`, and marks `"evaluate_values"` as completed.

4. **Generate Clinical Summary (`generate_summary`)**:
   The LLM synthesizes document details and evaluation findings into a final clinical analysis summary, citing document identifiers, reference ranges, and abnormal indicators without hallucinating diagnoses. Sets task status to `TaskStatus.COMPLETED`.

---

## 3. Persistence Architecture (`SQLiteStateStore`)

Persistence is completely decoupled from agent business logic via the `StateStore` protocol:

```python
class StateStore(Protocol):
    def save_state(self, state: AgentState) -> None: ...
    def load_state(self, task_id: str) -> AgentState | None: ...
    def save_messages(self, task_id: str, messages: Sequence[Message]) -> None: ...
    def load_messages(self, task_id: str) -> list[Message]: ...
    def save_checkpoint(
        self, state: AgentState, messages: Sequence[Message]
    ) -> None: ...
    def load_checkpoint(
        self, task_id: str
    ) -> tuple[AgentState, list[Message]] | None: ...
    def list_tasks(self) -> list[dict[str, Any]]: ...
    def delete_task(self, task_id: str) -> bool: ...
```

### Database Schema

Standard library `sqlite3` manages two relational tables:

```sql
CREATE TABLE IF NOT EXISTS agent_states (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    document_id TEXT,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    sequence_num INTEGER NOT NULL,
    role TEXT NOT NULL,
    message_json TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES agent_states(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_task_seq
ON conversation_messages(task_id, sequence_num);
```

### Atomic Checkpointing

`save_checkpoint(state, messages)` executes inside an explicit SQLite transaction. If an application process crashes or disk write fails, the database remains in its last consistent state without orphaned records or corrupted turns.

---

## 4. Task Interruption and Resumption

### The Resumption Lifecycle

```text
[Application 1: Run Task]
        │
        ├─ Iteration 1: search_lab_documents  --> Checkpoint saved
        ├─ Iteration 2: get_document_details  --> Checkpoint saved
        │
   [Process Killed / Crash]
   (Database contains: document_id="LAB-1002", extracted_values=[...], status="interrupted")
        │
[Application 2: Restart & Resume]
        │
        ├─ Load checkpoint from SQLite (task_id="interrupted-task-42")
        ├─ Restore AgentState and Message transcript
        ├─ Notice "search_document" and "extract_values" are completed
        ├─ Provide restored context to ModelClient
        ├─ Model sees document details in history, skips repeating search
        ├─ Iteration 3: evaluate_lab_results --> Checkpoint saved
        ├─ Iteration 4: Final Summary Answer  --> Status="completed", Checkpoint saved
        │
[Complete]
```

### Avoiding Duplicate Executions (Idempotency)

When a task is resumed:
1. The conversation history already contains the previous `ToolCall` and `ToolMessage` turns.
2. The restored prompt sent to the LLM already displays the search and extraction outcomes.
3. The LLM directly issues the next logical step (e.g., evaluation) without re-requesting completed queries.
4. If a completed task is resumed, `resume_agent` immediately returns the existing answer and state without issuing redundant model calls.

### Mid-Turn Crash Recovery

If the application terminated immediately after the model produced tool calls but before tool execution finished:
- `resume_agent` detects that the final message in the restored history is an `AssistantMessage` with unfulfilled tool calls.
- It executes the pending tool calls, appends the corresponding `ToolMessage`s, updates `AgentState`, and persists the repaired checkpoint before calling the model.

---

## 5. Failure Scenarios and Recovery Strategies

| Failure Mode | Impact | Recovery Strategy |
|---|---|---|
| **Process crash / power loss** | Process terminates mid-loop. | State is preserved at the last atomic checkpoint. Resuming with `--resume --task-id <id>` continues seamlessly. |
| **Model API error (`ModelError`)** | HTTP failure, rate limit, timeout. | State is updated to `TaskStatus.FAILED` with error text and checkpointed. Can be retried or resumed once connectivity recovers. |
| **Tool argument error** | Model passed invalid JSON or wrong arguments. | Returned to model as `ToolMessage(is_error=True)` so model can self-correct in the next turn. |
| **Iteration limit exceeded** | Task exceeded max iterations. | State is updated to `TaskStatus.INTERRUPTED` and saved. Resuming with higher `--max-iterations` allows continuation. |
| **Missing document lookup** | Document ID not found. | Returned as `DocumentNotFoundError` tool error result. Agent state remains consistent. |

---

## 6. Command Line Interface

The CLI fully supports persistence, listing, inspection, and task resumption:

```bash
# 1. Run a task with SQLite persistence
python -m lab_agent --db agent_state.db --task-id task-001 "Analyze thyroid panel"

# 2. List all persisted tasks
python -m lab_agent --db agent_state.db --list-tasks

# 3. Inspect structured agent state
python -m lab_agent --db agent_state.db --task-id task-001 --show-state

# 4. Resume an interrupted task
python -m lab_agent --db agent_state.db --task-id task-001 --resume
```
