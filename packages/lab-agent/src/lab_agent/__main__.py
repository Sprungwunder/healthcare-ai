"""Command line interface for the synthetic lab document agent.

Usage: ``python -m lab_agent [--provider P] [--trace] [--db PATH] "question"``.
``--provider openai`` (default) reads OPENAI_API_KEY (and optionally
OPENAI_MODEL, OPENAI_BASE_URL); ``--provider anthropic`` reads
ANTHROPIC_API_KEY (and optionally ANTHROPIC_MODEL, ANTHROPIC_BASE_URL).
``--trace`` prints the tool calls and results to stderr.
``--db`` enables SQLite persistence for state and conversation checkpoints.
``--resume`` continues an interrupted task specified by ``--task-id``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence

from lab_agent.agent import (
    DEFAULT_MAX_ITERATIONS,
    MaxIterationsExceededError,
    resume_agent,
    run_agent,
)
from lab_agent.anthropic_client import AnthropicMessagesClient
from lab_agent.model import (
    AssistantMessage,
    Message,
    ModelClient,
    ModelError,
    ToolMessage,
)
from lab_agent.openai_client import OpenAIChatClient
from lab_agent.storage import SQLiteStateStore, StorageError

PROVIDERS: dict[str, Callable[[], ModelClient]] = {
    "openai": OpenAIChatClient.from_env,
    "anthropic": AnthropicMessagesClient.from_env,
}


def main(argv: Sequence[str] | None = None, client: ModelClient | None = None) -> int:
    """Run the agent once or resume a task; return the process exit code."""
    parser = argparse.ArgumentParser(
        prog="lab_agent", description="Ask questions about synthetic lab documents."
    )
    parser.add_argument("question", nargs="?", default=None, help="question to answer")
    parser.add_argument(
        "--provider", choices=sorted(PROVIDERS), default="openai", help="model API"
    )
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    parser.add_argument(
        "--trace", action="store_true", help="print tool calls and results"
    )
    parser.add_argument(
        "--db", type=str, default=None, help="path to SQLite state database"
    )
    parser.add_argument("--task-id", type=str, default=None, help="task identifier")
    parser.add_argument("--resume", action="store_true", help="resume an existing task")
    parser.add_argument(
        "--list-tasks", action="store_true", help="list persisted tasks in database"
    )
    parser.add_argument(
        "--show-state", action="store_true", help="show structured state for --task-id"
    )
    args = parser.parse_args(argv)

    if args.list_tasks:
        if not args.db:
            print("error: --db is required to list tasks.", file=sys.stderr)
            return 1
        try:
            list_store = SQLiteStateStore(args.db)
            tasks = list_store.list_tasks()
            for t in tasks:
                doc_str = t.get("document_id") or "-"
                print(
                    f"{t['task_id']} | status: {t['status']} | "
                    f"doc: {doc_str} | updated: {t['updated_at']}"
                )
            return 0
        except StorageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if args.show_state:
        if not args.db or not args.task_id:
            print(
                "error: --db and --task-id are required to show state.", file=sys.stderr
            )
            return 1
        try:
            show_store = SQLiteStateStore(args.db)
            state = show_store.load_state(args.task_id)
            if state is None:
                print(f"error: task '{args.task_id}' not found.", file=sys.stderr)
                return 1
            print(json.dumps(state.to_dict(), indent=2))
            return 0
        except StorageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    store: SQLiteStateStore | None = None
    if args.db:
        try:
            store = SQLiteStateStore(args.db)
        except StorageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    try:
        if args.resume:
            if not args.task_id:
                print("error: --task-id is required to resume a task.", file=sys.stderr)
                return 1
            if store is None:
                print("error: --db is required to resume a task.", file=sys.stderr)
                return 1
            result = resume_agent(
                task_id=args.task_id,
                client=client or PROVIDERS[args.provider](),
                store=store,
                max_iterations=args.max_iterations,
            )
        else:
            if not args.question:
                parser.error("the following arguments are required: question")
            result = run_agent(
                args.question,
                client=client or PROVIDERS[args.provider](),
                max_iterations=args.max_iterations,
                task_id=args.task_id,
                store=store,
            )
    except (ModelError, MaxIterationsExceededError, ValueError, StorageError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.trace:
        _print_trace(result.messages)
    print(result.answer)
    return 0


def _print_trace(messages: Sequence[Message]) -> None:
    for message in messages:
        if isinstance(message, AssistantMessage):
            for call in message.tool_calls:
                print(f"-> {call.name}({call.arguments})", file=sys.stderr)
        elif isinstance(message, ToolMessage):
            print(f"<- {message.content}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
