"""Small conversational agent with one local tool."""

import concurrent.futures
import inspect

from .llm import LLM
from .prompt import system_prompt
from .tools import ALL_TOOLS
from .tools.agent import AgentTool
from .tools.todo import TodoWriteTool


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
        configured_tools = tools if tools is not None else ALL_TOOLS
        # AgentTool keeps a parent reference, so give each Agent its own
        # instance even when the default registry is shared globally.
        self.tools = [AgentTool() if isinstance(tool, AgentTool) else tool for tool in configured_tools]
        self.max_context_tokens = max_context_tokens
        self.max_rounds = max_rounds
        self.permission = permission
        self.messages: list[dict] = []
        self._tool_by_name = {tool.name: tool for tool in self.tools}
        self._system = system_prompt(self.tools)
        self._todo = next((tool for tool in self.tools if isinstance(tool, TodoWriteTool)), None)

        # Give the delegation tool access to this agent without introducing a
        # module-level dependency from AgentTool back to Agent.
        for tool in self.tools:
            if isinstance(tool, AgentTool):
                tool.bind_parent(self)

    def _full_messages(self) -> list[dict]:
        """Return system instructions followed by the conversation history."""
        system = self._system
        if self._todo is not None:
            rendered = self._todo.render()
            if rendered:
                system += "\n\n# Current task list\n" + rendered
        return [{"role": "system", "content": system}] + self.messages

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
            try:
                if len(response.tool_calls) == 1:
                    tool_call = response.tool_calls[0]
                    if on_tool:
                        on_tool(tool_call.name, tool_call.arguments)
                    result = self._permit(tool_call.name, tool_call.arguments)
                    if result is None:
                        result = self._execute_tool(tool_call.name, tool_call.arguments)
                    results = [result]
                else:
                    results = self._execute_tools_parallel(response.tool_calls, on_tool)
                for tool_call, result in zip(response.tool_calls, results):
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
            except KeyboardInterrupt:
                self._answer_pending_tool_calls(response.tool_calls)
                raise

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

    def _execute_tools_parallel(self, tool_calls, on_tool=None) -> list[str]:
        """Run a model's batch of calls concurrently, preserving result order."""
        from .tools.bash import get_tracked_cwd, set_tracked_cwd

        for tool_call in tool_calls:
            if on_tool:
                on_tool(tool_call.name, tool_call.arguments)

        # Resolve consent before starting workers so terminal prompts stay ordered.
        results: list[str | None] = []
        for tool_call in tool_calls:
            results.append(self._permit(tool_call.name, tool_call.arguments))

        session_cwd = get_tracked_cwd()

        def run_tool(index: int, tool_call, base_cwd: str | None):
            is_bash = tool_call.name == "bash"
            if is_bash:
                set_tracked_cwd(base_cwd)
            result = self._execute_tool(tool_call.name, tool_call.arguments)
            cwd_after = get_tracked_cwd() if is_bash else None
            changed_cwd = cwd_after if is_bash and cwd_after != base_cwd else None
            return index, result, changed_cwd

        futures = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for index, tool_call in enumerate(tool_calls):
                if results[index] is None:
                    futures[index] = pool.submit(run_tool, index, tool_call, session_cwd)

            # Collecting futures in input order preserves protocol ordering and
            # makes any reported Bash cwd changes deterministic.
            for index, future in futures.items():
                _, results[index], worker_cwd = future.result()
                if worker_cwd is not None:
                    session_cwd = worker_cwd
                    set_tracked_cwd(worker_cwd)

        return [result if result is not None else "" for result in results]

    def _answer_pending_tool_calls(self, tool_calls) -> None:
        """Keep the next provider request valid after an interrupted batch."""
        answered = {
            message.get("tool_call_id")
            for message in self.messages
            if message.get("role") == "tool"
        }
        for tool_call in tool_calls:
            if tool_call.id not in answered:
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": "[interrupted]",
                })

    def reset(self) -> None:
        """Clear the conversation history."""
        self.messages.clear()
        if self._todo is not None:
            self._todo._tasks = []
