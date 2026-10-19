"""Tests for TodoWriteTool registration and agent integration."""

import unittest

from src.agent import Agent
from src.tools import ALL_TOOLS
from src.tools.agent import AgentTool
from src.tools.todo import TodoWriteTool


class FakeReply:
    def __init__(self, content="", tool_calls=()):
        self.content = content
        self.tool_calls = list(tool_calls)
        self.message = {"role": "assistant", "content": content}


class RecordingLLM:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.requests = []

    def chat(self, **kwargs):
        self.requests.append(kwargs)
        return self.replies.pop(0)


class TodoWriteToolTests(unittest.TestCase):
    def test_registered_and_replaces_or_clears_full_checklist(self):
        self.assertIn("todo_write", [tool.name for tool in ALL_TOOLS])
        todo = TodoWriteTool()

        result = todo.execute(tasks=[
            {"content": "  Inspect files  ", "status": "in_progress"},
            {"content": "Run checks", "status": "pending"},
        ])
        self.assertIn("1. [in_progress] Inspect files", result)
        self.assertIn("2. [pending] Run checks", todo.render())

        error = todo.execute(tasks=[{"content": "Invalid task", "status": "later"}])
        self.assertIn("invalid status", error)
        self.assertIn("1. [in_progress] Inspect files", todo.render())

        self.assertEqual(todo.execute(tasks=[]), "Task list cleared.")
        self.assertEqual(todo.render(), "")

    def test_agent_injects_current_list_and_reset_clears_it(self):
        todo = TodoWriteTool()
        todo.execute(tasks=[{"content": "Check prompt injection", "status": "in_progress"}])
        llm = RecordingLLM([FakeReply("done")])
        agent = Agent(llm=llm, tools=[todo])

        agent.chat("continue")
        system_message = llm.requests[0]["messages"][0]["content"]
        self.assertIn("# Current task list", system_message)
        self.assertIn("1. [in_progress] Check prompt injection", system_message)

        agent.reset()
        self.assertEqual(todo.render(), "")
        self.assertNotIn("# Current task list", agent._full_messages()[0]["content"])

    def test_sub_agent_shares_parent_checklist(self):
        todo = TodoWriteTool()
        todo.execute(tasks=[{"content": "Shared child task", "status": "pending"}])
        llm = RecordingLLM([FakeReply("child finished")])
        parent = Agent(llm=llm, tools=[todo, AgentTool()])

        result = parent._execute_tool("agent", {"task": "inspect shared checklist"})

        self.assertIn("child finished", result)
        child_system = llm.requests[0]["messages"][0]["content"]
        self.assertIn("1. [pending] Shared child task", child_system)


if __name__ == "__main__":
    unittest.main()
