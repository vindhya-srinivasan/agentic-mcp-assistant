import asyncio

import pytest
from dotenv import load_dotenv

from agent import build_graph, run_turn
from mcp_client import load_mcp_tools

load_dotenv()


@pytest.fixture(scope="module")
def run():
    """One event loop for the whole module, like FastAPI in production."""
    with asyncio.Runner() as runner:
        yield runner.run


async def _graph():
    tools, _ = await load_mcp_tools("mcp_config.json")
    return build_graph(tools)

def test_uses_filesystem_tool(run):
    async def scenario():
        graph = await _graph()
        return await run_turn(graph, "What does the file sample.txt say?", "fs-test")

    assert "hello" in run(scenario()).lower()


def test_answers_without_tools(run):
    async def scenario():
        graph = await _graph()
        await run_turn(graph, "What is 12 times 12?", "no-tool-test")
        state = await graph.aget_state({"configurable": {"thread_id": "no-tool-test"}})
        return state.values["messages"]

    messages = run(scenario())
    assert "144" in messages[-1].content
    assert not any(m.type == "tool" for m in messages)


def test_memory_is_session_scoped(run):
    async def scenario():
        graph = await _graph()
        await run_turn(graph, "My favorite color is teal. Just say OK.", "session-a")
        same = await run_turn(graph, "What is my favorite color?", "session-a")
        other = await run_turn(graph, "What is my favorite color?", "session-b")
        return same, other

    same, other = run(scenario())
    assert "teal" in same.lower()
    assert "teal" not in other.lower()