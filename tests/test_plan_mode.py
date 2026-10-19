"""Tests for the read-only planning workflow."""

import unittest
from unittest.mock import patch

from src.agent import Agent
from src.cli import _repl
from src.permissions import Permission
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
        self.message = {"role": "assistant", "content": content or None}


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def chat(self, **kwargs):
        self.requests.append(kwargs)
        return self.replies.pop(0)


class ProbeTool(Tool):
    description = "Test tool"
    parameters = {"type": "object", "properties": {}}

    def __init__(self, name):
        self.name = name
        self.calls = 0

    def execute(self):
        self.calls += 1
        return "executed"


class PlanModeTests(unittest.TestCase):
    def test_plan_prompt_is_only_added_while_plan_mode_is_enabled(self):
        llm = ScriptedLLM([FakeReply("done"), FakeReply("plan done")])
        agent = Agent(llm=llm, tools=[])

        agent.chat("normal")
        self.assertNotIn("# Plan mode", llm.requests[0]["messages"][0]["content"])

        agent.plan_mode = True
        agent.chat("plan this")
        self.assertIn("# Plan mode", llm.requests[1]["messages"][0]["content"])

    def test_plan_mode_refuses_mutations_even_with_allow_all(self):
        writer = ProbeTool("write_file")
        llm = ScriptedLLM([
            FakeReply(tool_calls=[FakeToolCall("write_file", {}, "write-1")]),
            FakeReply("Here is the plan."),
        ])
        agent = Agent(
            llm=llm,
            tools=[writer],
            permission=Permission(allow_all=True),
        )
        agent.plan_mode = True

        self.assertEqual(agent.chat("plan a change"), "Here is the plan.")
        self.assertEqual(writer.calls, 0)
        refusal = next(m["content"] for m in agent.messages if m.get("role") == "tool")
        self.assertIn("Plan mode is on", refusal)

    def test_parallel_plan_mode_allows_reads_and_refuses_mutations(self):
        reader = ProbeTool("read_file")
        writer = ProbeTool("edit_file")
        llm = ScriptedLLM([
            FakeReply(tool_calls=[
                FakeToolCall("read_file", {}, "read-1"),
                FakeToolCall("edit_file", {}, "edit-1"),
            ]),
            FakeReply("Plan ready."),
        ])
        agent = Agent(
            llm=llm,
            tools=[reader, writer],
            permission=Permission(allow_all=True),
        )
        agent.plan_mode = True

        self.assertEqual(agent.chat("plan a change"), "Plan ready.")
        self.assertEqual(reader.calls, 1)
        self.assertEqual(writer.calls, 0)
        results = [m for m in agent.messages if m.get("role") == "tool"]
        self.assertEqual([m["tool_call_id"] for m in results], ["read-1", "edit-1"])
        self.assertEqual(results[0]["content"], "executed")
        self.assertIn("Plan mode is on", results[1]["content"])

    def test_cli_approval_exits_plan_mode_and_sends_approval(self):
        llm = ScriptedLLM([FakeReply("Plan."), FakeReply("Implemented.")])
        agent = Agent(llm=llm, tools=[])
        user_inputs = iter(["/plan", "make a plan", "/approve"])

        def fake_input(_prompt):
            try:
                return next(user_inputs)
            except StopIteration:
                raise EOFError

        with patch("builtins.input", side_effect=fake_input), patch("src.cli.console.print"):
            _repl(agent, config=None)

        self.assertIn("# Plan mode", llm.requests[0]["messages"][0]["content"])
        self.assertEqual(llm.requests[1]["messages"][-1]["content"], "approve")
        self.assertNotIn("# Plan mode", llm.requests[1]["messages"][0]["content"])
        self.assertFalse(agent.plan_mode)


if __name__ == "__main__":
    unittest.main()
