"""Command line: ``python -m lab_agent [--trace] "question"``.

Reads OPENAI_API_KEY (and optionally OPENAI_MODEL, OPENAI_BASE_URL) from the
environment. ``--trace`` prints the tool calls and results to stderr.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from lab_agent.agent import (
    DEFAULT_MAX_ITERATIONS,
    MaxIterationsExceededError,
    run_agent,
)
from lab_agent.model import (
    AssistantMessage,
    Message,
    ModelClient,
    ModelError,
    ToolMessage,
)
from lab_agent.openai_client import OpenAIChatClient


def main(argv: Sequence[str] | None = None, client: ModelClient | None = None) -> int:
    """Run the agent once and print the answer; return the process exit code."""
    parser = argparse.ArgumentParser(
        prog="lab_agent", description="Ask questions about synthetic lab documents."
    )
    parser.add_argument("question")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    parser.add_argument(
        "--trace", action="store_true", help="print tool calls and results"
    )
    args = parser.parse_args(argv)

    try:
        result = run_agent(
            args.question,
            client or OpenAIChatClient.from_env(),
            max_iterations=args.max_iterations,
        )
    except (ModelError, MaxIterationsExceededError) as exc:
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
