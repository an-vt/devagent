"""Tests for concurrent tool-call handling and hook flow."""

import threading
import time
import unittest
from unittest.mock import patch

from src.agent import Agent
from src.permissions import Permission
from src.tools.agent import AgentTool
from src.tools.base import Tool


class FakeToolCall:
    def __init__(self, name, arguments, call_id):
        self.name = name
        self.arguments = arguments
        self.id = call_id


class FakeReply:
    def __init__(self, content="", tool_calls=()):
        self.content = content
        self.tool_calls = list(tool_calls)
        self.message = {"role": "assistant", "content": content}


class ProbeTool(Tool):
    name = "probe"
    description = "A test tool that blocks until both sub-agents reach it."
    parameters = {
        "type": "object",
        "properties": {"task": {"type": "string"}},
        "required": ["task"],
    }

    def __init__(self, barrier):
        self.barrier = barrier

    def execute(self, task: str) -> str:
        self.barrier.wait(timeout=2)
        return f"probe:{task}"


class DelegationLLM:
    """Return two parent delegations and one probe call per child."""

    def __init__(self):
        self.child_barrier = threading.Barrier(2)

    def chat(self, messages, **_kwargs):
        user_content = next(m["content"] for m in messages if m["role"] == "user")
        if messages[-1]["role"] == "user" and user_content == "delegate":
            return FakeReply(tool_calls=[
                FakeToolCall("agent", {"task": "subtask-1"}, "agent-1"),
                FakeToolCall("agent", {"task": "subtask-2"}, "agent-2"),
            ])
        if messages[-1]["role"] == "user" and user_content.startswith("subtask-"):
            self.child_barrier.wait(timeout=2)
            return FakeReply(tool_calls=[
                FakeToolCall("probe", {"task": user_content}, f"probe-{user_content}")
            ])
        if messages[-1]["role"] == "tool" and user_content.startswith("subtask-"):
            return FakeReply(f"finished {user_content}")
        if messages[-1]["role"] == "tool" and user_content == "delegate":
            return FakeReply("parent finished")
        raise AssertionError(f"Unexpected model request: {messages}")


class AgentParallelTests(unittest.TestCase):
    def test_multiple_agent_calls_run_concurrently_and_keep_result_order(self):
        main_thread = threading.get_ident()
        probe = ProbeTool(threading.Barrier(2))
        prompt_lock = threading.Lock()
        prompt_state = {"active": 0, "max_active": 0, "calls": []}

        def ask(name, _arguments):
            with prompt_lock:
                prompt_state["active"] += 1
                prompt_state["max_active"] = max(
                    prompt_state["max_active"], prompt_state["active"]
                )
                prompt_state["calls"].append((name, threading.get_ident()))
            time.sleep(0.01)
            with prompt_lock:
                prompt_state["active"] -= 1
            return "once"

        permission = Permission(ask=ask)
        agent = Agent(
            llm=DelegationLLM(),
            tools=[AgentTool(), probe],
            permission=permission,
        )

        self.assertEqual(agent.chat("delegate"), "parent finished")
        tool_results = [m for m in agent.messages if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in tool_results], ["agent-1", "agent-2"])
        self.assertIn("finished subtask-1", tool_results[0]["content"])
        self.assertIn("finished subtask-2", tool_results[1]["content"])

        self.assertEqual(prompt_state["max_active"], 1)
        agent_prompt_threads = [thread_id for name, thread_id in prompt_state["calls"] if name == "agent"]
        self.assertEqual(agent_prompt_threads, [main_thread, main_thread])
        probe_prompt_threads = [thread_id for name, thread_id in prompt_state["calls"] if name == "probe"]
        self.assertEqual(len(probe_prompt_threads), 2)
        self.assertTrue(all(thread_id != main_thread for thread_id in probe_prompt_threads))

    def test_interrupted_batch_backfills_each_unanswered_tool_call(self):
        tool_calls = [
            FakeToolCall("unknown", {}, "pending-1"),
            FakeToolCall("unknown", {}, "pending-2"),
        ]

        class InterruptingLLM:
            def chat(self, **_kwargs):
                return FakeReply(tool_calls=tool_calls)

        agent = Agent(llm=InterruptingLLM(), tools=[])
        with self.assertRaises(KeyboardInterrupt):
            with patch.object(agent, "_execute_tools_parallel", side_effect=KeyboardInterrupt):
                agent.chat("interrupt me")

        self.assertEqual(
            [
                (message["tool_call_id"], message["content"])
                for message in agent.messages
                if message["role"] == "tool"
            ],
            [("pending-1", "[interrupted]"), ("pending-2", "[interrupted]")],
        )


if __name__ == "__main__":
    unittest.main()
