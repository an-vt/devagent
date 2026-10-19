"""Conversation-size estimation and automatic history compression."""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .llm import LLM


_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffef]")
_SYMBOL_RE = re.compile(r"[^\w\s]")


def _approx_tokens(text: str) -> int:
    """Estimate token count for prose, code, and CJK text."""
    cjk = len(_CJK_RE.findall(text))
    rest = len(text) - cjk
    dense = rest > 0 and len(_SYMBOL_RE.findall(text)) / len(text) > 0.25
    return math.ceil(cjk / 1.5) + int(rest / (2.8 if dense else 3.4))


def estimate_tokens(messages: list[dict]) -> int:
    """Estimate the size of conversation messages, including tool calls."""
    total = 0
    for message in messages:
        content = message.get("content")
        if content:
            total += _approx_tokens(content)
        tool_calls = message.get("tool_calls")
        if tool_calls:
            total += _approx_tokens(str(tool_calls))
    return total


class ContextManager:
    """Trim large tool outputs and summarize older conversation when needed."""

    def __init__(self, max_tokens: int = 128_000):
        self.max_tokens = max_tokens
        self._snip_at = int(max_tokens * 0.50)
        self._summarize_at = int(max_tokens * 0.70)
        self._collapse_at = int(max_tokens * 0.90)

    def maybe_compress(self, messages: list[dict], llm: LLM | None = None) -> bool:
        """Compress messages when over a configured threshold; return if changed."""
        current = estimate_tokens(messages)
        compressed = False

        if current > self._snip_at and self._snip_tool_outputs(messages):
            compressed = True
            current = estimate_tokens(messages)

        if (
            current > self._summarize_at
            and len(messages) > 10
            and self._summarize_old(messages, llm, keep_recent=8)
        ):
            compressed = True
            current = estimate_tokens(messages)

        if current > self._collapse_at and len(messages) > 4:
            self._hard_collapse(messages, llm)
            compressed = True

        return compressed

    @staticmethod
    def _snip_tool_outputs(messages: list[dict]) -> bool:
        """Keep the first and last lines of large tool responses."""
        changed = False
        for message in messages:
            if message.get("role") != "tool":
                continue
            content = message.get("content", "")
            if len(content) <= 1500:
                continue
            lines = content.splitlines()
            if len(lines) <= 6:
                continue
            message["content"] = (
                "\n".join(lines[:3])
                + f"\n... ({len(lines)} lines, snipped to save context) ...\n"
                + "\n".join(lines[-3:])
            )
            changed = True
        return changed

    @staticmethod
    def _safe_split(messages: list[dict], keep_recent: int) -> int:
        """Avoid starting the retained tail with an orphaned tool result."""
        split = max(0, len(messages) - keep_recent)
        while split > 0 and messages[split].get("role") == "tool":
            split -= 1
        return split

    def _summarize_old(
        self, messages: list[dict], llm: LLM | None, keep_recent: int = 8
    ) -> bool:
        """Replace older turns with a summary and retain the recent messages."""
        if len(messages) <= keep_recent:
            return False

        split = self._safe_split(messages, keep_recent)
        summary = self._get_summary(messages[:split], llm)
        tail = messages[split:]

        messages.clear()
        messages.extend(
            [
                {
                    "role": "user",
                    "content": f"[Context compressed - conversation summary]\n{summary}",
                },
                {
                    "role": "assistant",
                    "content": "Got it, I have the context from our earlier conversation.",
                },
                *tail,
            ]
        )
        return True

    def _hard_collapse(self, messages: list[dict], llm: LLM | None) -> None:
        """Keep the latest four messages plus a summary of the older history."""
        split = self._safe_split(messages, 4 if len(messages) > 4 else 2)
        summary = self._get_summary(messages[:split], llm)
        tail = messages[split:]

        messages.clear()
        messages.extend(
            [
                {"role": "user", "content": f"[Hard context reset]\n{summary}"},
                {
                    "role": "assistant",
                    "content": "Context restored. Continuing from where we left off.",
                },
                *tail,
            ]
        )

    def _get_summary(self, messages: list[dict], llm: LLM | None) -> str:
        """Summarize with the configured LLM, falling back to local extraction."""
        flattened = self._flatten(messages)
        if llm is not None:
            try:
                response = llm.chat(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Compress this conversation into a brief summary. "
                                "Preserve: file paths edited, key decisions made, "
                                "errors encountered, current task state. "
                                "Drop: verbose command output, code listings, "
                                "redundant back-and-forth."
                            ),
                        },
                        {"role": "user", "content": flattened[:15_000]},
                    ],
                )
                if response.content:
                    return response.content
            except Exception:  # noqa: BLE001
                # Compression is best effort; retain a useful local summary.
                pass

        return self._extract_key_info(messages)

    @staticmethod
    def _flatten(messages: list[dict]) -> str:
        parts = []
        for message in messages:
            role = message.get("role", "?")
            text = message.get("content", "") or ""
            if text:
                parts.append(f"[{role}] {text[:400]}")
        return "\n".join(parts)

    @staticmethod
    def _extract_key_info(messages: list[dict]) -> str:
        """Extract file paths and errors when an LLM summary is unavailable."""
        files_seen = set()
        errors = []

        for message in messages:
            text = message.get("content", "") or ""
            for match in re.finditer(r"[\w./\-]+\.\w{1,5}", text):
                files_seen.add(match.group())
            for line in text.splitlines():
                if "error" in line.lower():
                    errors.append(line.strip()[:150])

        parts = []
        if files_seen:
            parts.append(f"Files touched: {', '.join(sorted(files_seen)[:20])}")
        if errors:
            parts.append(f"Errors seen: {'; '.join(errors[:5])}")
        return "\n".join(parts) or "(no extractable context)"
