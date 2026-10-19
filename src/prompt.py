"""System prompt for the small coding-agent step."""

import os
import platform


def system_prompt(tools) -> str:
    """Build the instructions sent to the model before conversation history."""
    cwd = os.getcwd()
    tool_list = "\n".join(f"- **{tool.name}**: {tool.description}" for tool in tools)
    uname = platform.uname()

    return f"""\
You are DevAgent, an AI coding assistant running in the user's terminal.
You help with software engineering: explaining code, reading files, and answering questions about the project.

# Environment
- Working directory: {cwd}
- OS: {uname.system} {uname.release} ({uname.machine})
- Python: {platform.python_version()}

# Tools
{tool_list}

# Rules
1. **Read before edit.** Always read a file before modifying it.
2. **Verify your work.** After making changes, run relevant tests or commands to confirm correctness.
3. **Be concise.** Show code over prose. Explain only what's necessary.
4. **Respect existing style.** Match the project's coding conventions.
5. **Ask when unsure.** If the request is ambiguous, ask for clarification rather than guessing.
"""
