"""Command-line entry point for devagent."""

import argparse
import logging
import sys

from prompt_toolkit import prompt as pt_prompt
from rich.console import Console

from src.agent import Agent
from src.llm import LLM
from src.permissions import DEFAULT_STORE, Permission
from src.tools import ALL_TOOLS

from .config import Config

logger = logging.getLogger(__name__)

console = Console()
err_console = Console(stderr=True)


def _parse_args():
    p = argparse.ArgumentParser(
        prog="devagent",
        description="Minimal AI coding agent. Works with any OpenAI-compatible LLM.",
    )
    p.add_argument("--yes", action="store_true", help="Auto-approve every tool call")
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

    llm = LLM(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )

    agent = Agent(
        llm=llm,
        tools=[*ALL_TOOLS],
        # tools=[*ALL_TOOLS, *load_mcp_tools()],
        max_context_tokens=config.max_context_tokens,
        permission=Permission(allow_all=args.yes)
        if args.yes
        else Permission(ask=_ask_permission, persist_path=DEFAULT_STORE),
        # hooks=load_hooks(),
    )

    # interactive REPL
    _repl(agent, config)


def _repl(agent: Agent, config: Config):
    """Interactive read-eval-print loop."""

    console.print("Welcome to devagent!")

    while True:
        try:
            user_input = input("devagent> ")
        except KeyboardInterrupt:
            console.print("\nExiting REPL.")
            break
        except EOFError:
            console.print("\nExiting REPL.")
            break

        if not user_input.strip():
            continue

        try:
            streamed: list[str] = []
            reasoning_streamed: list[str] = []
            answer_started = False

            def on_token(token: str, streamed=streamed, reasoning_streamed=reasoning_streamed) -> None:
                nonlocal answer_started
                if reasoning_streamed and not answer_started:
                    print("\n\nAnswer:\n", end="", flush=True)
                    answer_started = True
                streamed.append(token)
                print(token, end="", flush=True)

            def on_reasoning(token: str, reasoning_streamed=reasoning_streamed) -> None:
                if not reasoning_streamed:
                    console.print("\nReasoning:\n", style="dim", end="")
                reasoning_streamed.append(token)
                console.print(token, style="dim", end="")

            def on_tool(name: str, arguments: dict) -> None:
                console.print(f"\n[dim]> {name}({arguments})[/dim]")

            response = agent.chat(
                user_input,
                on_token=on_token,
                on_tool=on_tool,
                on_reasoning=on_reasoning,
            )
            if streamed:
                print()
            else:
                print(response)
        except Exception as exc:
            logger.exception("Agent request failed")
            console.print(f"[red]Error: {exc}[/red]")


def _brief(arguments: dict) -> str:
    """Keep approval prompts readable when tool arguments contain file text."""
    rendered = repr(arguments)
    return rendered if len(rendered) <= 500 else rendered[:497] + "..."


def _ask_permission(tool_name: str, arguments: dict) -> str:
    """Prompt until the user allows once, always, or denies the call."""
    console.print(
        f"\n[bold yellow]permission requested:[/] "
        f"[cyan]{tool_name}[/cyan]({_brief(arguments)})"
    )
    try:
        answer = pt_prompt("  [y] allow once  [a] always allow this tool  [n] deny: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print("[dim]denied[/dim]")
        return "deny"
    if answer in ("y", "yes"):
        return "once"
    if answer in ("a", "always"):
        return "always"
    return "deny"
