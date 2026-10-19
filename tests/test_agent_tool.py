"""Tests for synchronous sub-agent delegation."""

import unittest

from src.agent import Agent
from src.tools import ALL_TOOLS
from src.tools.bash import get_tracked_cwd, set_tracked_cwd


class FakeToolCall:
    def __init__(self, name, arguments, call_id="call-1"):
        self.name = name
        self.arguments = arguments
        self.id = call_id


class FakeReply:
    def __init__(self, content="", tool_calls=()):
        self.content = content
        self.tool_calls = list(tool_calls)
        self.message = {"role": "assistant", "content": content}


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def chat(self, **kwargs):
        self.requests.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class RecordingPermission:
    def __init__(self):
        self.calls = []

    def check(self, name, arguments):
        self.calls.append((name, arguments))
        return None


class AgentToolTests(unittest.TestCase):
    def make_agent(self, llm, permission=None):
        return Agent(llm=llm, tools=[*ALL_TOOLS], max_context_tokens=4096, permission=permission)

    def test_registered_agent_delegates_synchronously_without_recursive_tool(self):
        llm = ScriptedLLM([
            FakeReply(tool_calls=[FakeToolCall("agent", {"task": "inspect the project"})]),
            FakeReply("sub-agent result"),
            FakeReply("parent result"),
        ])
        permission = RecordingPermission()
        agent = self.make_agent(llm, permission)
        other_agent = self.make_agent(ScriptedLLM([FakeReply("unused")]))

        self.assertIn("agent", [tool.name for tool in agent.tools])
        self.assertIs(agent._tool_by_name["agent"]._parent_agent, agent)
        self.assertIs(other_agent._tool_by_name["agent"]._parent_agent, other_agent)
        result = agent.chat("delegate research")

        self.assertEqual(result, "parent result")
        self.assertEqual(len(llm.requests), 3)
        child_request = llm.requests[1]
        self.assertEqual([m["role"] for m in child_request["messages"]], ["system", "user"])
        self.assertEqual(child_request["messages"][-1]["content"], "inspect the project")
        self.assertNotIn("agent", [s["function"]["name"] for s in child_request["tools"]])
        self.assertEqual([name for name, _ in permission.calls], ["agent"])
        self.assertIn("[Sub-agent completed]\nsub-agent result", agent.messages[2]["content"])

    def test_subagent_shares_permission_and_restores_tracked_working_directory(self):
        llm = ScriptedLLM([
            FakeReply(tool_calls=[FakeToolCall("agent", {"task": "change directory"})]),
            FakeReply(tool_calls=[FakeToolCall("bash", {"command": "cd /"})]),
            FakeReply("finished"),
            FakeReply("parent finished"),
        ])
        permission = RecordingPermission()
        agent = self.make_agent(llm, permission)
        prior_cwd = "/tmp"
        set_tracked_cwd(prior_cwd)
        try:
            agent.chat("delegate")
            self.assertEqual(get_tracked_cwd(), prior_cwd)
        finally:
            set_tracked_cwd(None)

        self.assertEqual([name for name, _ in permission.calls], ["agent", "bash"])

    def test_subagent_errors_are_returned_as_tool_text(self):
        llm = ScriptedLLM([RuntimeError("model unavailable")])
        agent = self.make_agent(llm)

        result = agent._execute_tool("agent", {"task": "fail safely"})

        self.assertEqual(result, "Sub-agent error: model unavailable")

    def test_subagent_result_is_truncated(self):
        llm = ScriptedLLM([FakeReply("x" * 6000)])
        agent = self.make_agent(llm)

        result = agent._execute_tool("agent", {"task": "return a long result"})

        self.assertTrue(result.startswith("[Sub-agent completed]\n"))
        self.assertTrue(result.endswith("... (sub-agent output truncated)"))
        self.assertLess(len(result), 5000)


if __name__ == "__main__":
    unittest.main()
