"""LangGraph agent: an LLM reasoning node and an MCP tool node, with checkpointed memory."""

import os

from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

SYSTEM_PROMPT = """You are a helpful assistant with access to tools from several MCP servers.

How to decide:
- Files in the workspace (reading, writing, listing, editing): use the filesystem tools.
  Paths are relative to the workspace, e.g. "sample.txt".
- Current events, facts you are unsure of, or anything that needs a web search: use the search tool.
- The contents of a specific URL: use the fetch tool.
- General knowledge, reasoning, math, writing, or questions about this conversation:
  answer directly without calling any tool.

Chain tools when a task needs several steps (e.g. search, then fetch a result, then save a summary
to a file). If a tool returns an error, explain what went wrong instead of guessing the result.
Be concise."""

RECURSION_LIMIT = 20  # caps reasoning/tool loops so a confused model can't spin forever


def build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ["MODEL_NAME"],
        base_url=os.getenv("OPENAI_BASE_URL") or None,
        temperature=0,
    )


def build_graph(tools: list[BaseTool]):
    llm = build_llm()
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    async def call_model(state: MessagesState) -> dict:
        response = await llm_with_tools.ainvoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)  # tool calls -> "tools", else END
    graph.add_edge("tools", "agent")  # loop back so the LLM sees tool results
    return graph.compile(checkpointer=MemorySaver())


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content if isinstance(part, dict))


async def run_turn(graph, query: str, session_id: str) -> str:
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": RECURSION_LIMIT}
    result = await graph.ainvoke({"messages": [("user", query)]}, config=config)
    return _message_text(result["messages"][-1].content)