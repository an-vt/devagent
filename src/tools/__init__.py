"""Tool registry for devagent."""

from .bash import BashTool
from .agent import AgentTool
from .edit import EditFileTool
from .glob_tool import GlobTool
from .grep import GrepTool
from .read import ReadFileTool
from .todo import TodoWriteTool
from .write import WriteFileTool

ALL_TOOLS = [
    BashTool(),
    AgentTool(),
    ReadFileTool(),
    WriteFileTool(),
    EditFileTool(),
    GlobTool(),
    GrepTool(),
    TodoWriteTool(),
]
