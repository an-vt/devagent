"""Small conversational agent with one local tool."""

import inspect

from .llm import LLM
from .prompt import system_prompt
from .tools import ALL_TOOLS


class Agent:
    """Keep conversation history and ask the LLM for the next response."""

    def __init__(
        self,
        llm: LLM,
        tools: list | None = None,
        max_context_tokens: int = 128_000,
        max_rounds: int = 10,
        permission=None,
    ):
        self.llm = llm
        self.tools = tools if tools is not None else ALL_TOOLS
        self.max_context_tokens = max_context_tokens
        self.max_rounds = max_rounds
        self.permission = permission
        self.messages: list[dict] = []
        self._tool_by_name = {tool.name: tool for tool in self.tools}
        self._system = system_prompt(self.tools)

    def _full_messages(self) -> list[dict]:
        """Return system instructions followed by the conversation history."""
        return [{"role": "system", "content": self._system}] + self.messages

    def _tool_schemas(self) -> list[dict]:
        """Convert local tools to the provider's function-calling format."""
        return [tool.schema() for tool in self.tools]

    def chat(self, user_input: str, on_token=None, on_tool=None, on_reasoning=None) -> str:
        """Process one user message, executing tool calls until text is returned."""
        self.messages.append({"role": "user", "content": user_input})

        for _ in range(self.max_rounds):
            response = self.llm.chat(
                messages=self._full_messages(),
                tools=self._tool_schemas(),
                on_token=on_token,
                on_reasoning=on_reasoning,
            )

            # No tool call means the model has finished its answer.
            if not response.tool_calls:
                self.messages.append(response.message)
                return response.content

            # The assistant tool-call message must come before tool results.
            self.messages.append(response.message)
            for tool_call in response.tool_calls:
                if on_tool:
                    on_tool(tool_call.name, tool_call.arguments)
                result = self._permit(tool_call.name, tool_call.arguments)
                if result is None:
                    result = self._execute_tool(tool_call.name, tool_call.arguments)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        return "(reached maximum tool-call rounds)"

    def _permit(self, name: str, arguments: dict) -> str | None:
        """Ask for consent before a tool mutates state."""
        if self.permission is None:
            return None
        return self.permission.check(name, arguments)

    def _execute_tool(self, name: str, arguments: dict) -> str:
        """Execute one known tool and return errors as tool-readable text."""
        tool = self._tool_by_name.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'"
        try:
            inspect.signature(tool.execute).bind(**arguments)
        except TypeError as exc:
            return f"Error: bad arguments for {name}: {exc}"
        try:
            return tool.execute(**arguments)
        except Exception as exc:  # noqa: BLE001
            return f"Error executing {name}: {exc}"

    def reset(self) -> None:
        """Clear the conversation history."""
        self.messages.clear()
