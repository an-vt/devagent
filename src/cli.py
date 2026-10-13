"""Command-line entry point for devagent."""

import argparse
import logging
import time
import sys
from rich.console import Console
from prompt_toolkit.key_binding import KeyBindings

from .config import Config

logger = logging.getLogger(__name__)

console = Console()
err_console = Console(stderr=True)


def _parse_args():
    p = argparse.ArgumentParser(
        prog="devagent",
        description="Minimal AI coding agent. Works with any OpenAI-compatible LLM.",
    )
    return p.parse_args()


def main() -> None:
    """Load configuration and start the persistent interactive CLI."""
    args = _parse_args()

    config = Config.from_env()

    logging.basicConfig(level=config.log_level)

    if not config.api_key:
        console.print("[red bold]No API key found.[/]")
        console.print(
            "Set one of: OPENAI_API_KEY, DEEPSEEK_API_KEY"
            "\nExamples:\n"
            "  # OpenAI\n"
            "  export OPENAI_API_KEY=sk-...\n"
            "\n"
            "  # DeepSeek\n"
            "  export OPENAI_API_KEY=sk-... OPENAI_BASE_URL=https://api.deepseek.com\n"
        )
        sys.exit(1)

    # interactive REPL
    _repl(config)


def _repl(config: Config):
    """Interactive read-eval-print loop."""

    console.print(f"Welcome to devagent!")

    # Enter submits, Escape+Enter inserts a newline (for pasting code blocks etc.)
    kb = KeyBindings()

    while True:
        try:
            user_input = input("devagent> ")
        except KeyboardInterrupt:
            console.print("\nExiting REPL.")
            break
        except EOFError:
            # Ctrl+D should not be a shutdown path.  In an interactive TTY the
            # next input() call displays the prompt again; this also keeps the
            # container's main process alive when stdin is temporarily empty.
            try:
                time.sleep(0.1)
            except KeyboardInterrupt:
                console.print("\nExiting REPL.")
                break
            continue

        # Here you would typically process the user input and generate a response.
        logger.info("%s", user_input)
