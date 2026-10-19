"""User consent for tools that mutate local state.

Read-only tools run immediately.  Mutating tools ask the interactive CLI for
permission before they execute; a grant can apply once or to that tool for the
rest of the session (and, when configured, future sessions).
"""

import json
import threading
from pathlib import Path

DEFAULT_STORE = Path.home() / ".devagent" / "permissions.json"


class Permission:
    """Session-scoped consent state.

    ``ask(tool_name, arguments)`` should return ``"once"``, ``"always"``,
    or ``"deny"``.  With no callback, mutating calls are refused rather than
    blocking forever in non-interactive use.
    """

    READ_ONLY = frozenset({"read_file", "glob", "grep", "todo_write"})

    def __init__(
        self, ask=None, allow_all: bool = False, persist_path: Path | None = None
    ):
        self.ask = ask
        self.allow_all = allow_all
        self._always: set[str] = set()
        # Sub-agents can check permissions from different worker threads.
        # Keep interactive prompts and the persisted allow-list serialized.
        self._lock = threading.RLock()
        self._persist_path = persist_path
        if persist_path is not None:
            try:
                saved = json.loads(persist_path.read_text(encoding="utf-8"))
                self._always = {
                    tool for tool in saved.get("always", []) if isinstance(tool, str)
                }
            except (OSError, ValueError, AttributeError):
                pass

    def check(self, tool_name: str, arguments: dict) -> str | None:
        """Return a refusal message, or ``None`` when execution is allowed."""
        with self._lock:
            return self._check_locked(tool_name, arguments)

    def _check_locked(self, tool_name: str, arguments: dict) -> str | None:
        if tool_name in self.READ_ONLY or self.allow_all or tool_name in self._always:
            return None

        if self.ask is None:
            return (
                f"Permission denied: {tool_name} mutates state and this session is "
                "non-interactive, so nobody can approve it. Rerun with --yes, or "
                "tell the user the exact step so they can run it themselves."
            )

        verdict = self.ask(tool_name, arguments)
        if verdict == "always":
            self._always.add(tool_name)
            self._save()
            return None
        if verdict == "once":
            return None
        return (
            f"Permission denied: the user refused this {tool_name} call. "
            "Do not retry it unchanged; ask what they would prefer instead."
        )

    def _save(self) -> None:
        if self._persist_path is None:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(
                json.dumps({"always": sorted(self._always)}, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            # Permission persistence is convenience; it must not block a grant.
            pass
