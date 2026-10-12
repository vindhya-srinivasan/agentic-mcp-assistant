"""LangGraph agent: an LLM reasoning node and an MCP tool node, with checkpointed memory."""

import logging
import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

logger = logging.getLogger(__name__)

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
        base_url=os.getenv("OPENAI_BASE_URL") or None,  # blank = OpenAI, NIM URL = NVIDIA
        temperature=0,
        timeout=60,  # one LLM call can't hang the request forever
        max_retries=2,
    )


def _close_dangling_tool_calls(messages: list) -> list:
    """If a previous turn was interrupted mid-tool-call, add an error result for each
    unanswered call so the history stays valid for the LLM API."""
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    repaired = []
    for message in messages:
        repaired.append(message)
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                if call["id"] not in answered:
                    repaired.append(ToolMessage(
                        content="Error: this tool call was interrupted before it returned.",
                        tool_call_id=call["id"],
                    ))
    return repaired


def build_graph(tools: list[BaseTool]):
    llm = build_llm()
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    async def call_model(state: MessagesState) -> dict:
        # The system prompt is prepended per call, not stored, so memory holds only the conversation.
        history = _close_dangling_tool_calls(state["messages"])
        response = await llm_with_tools.ainvoke([SystemMessage(SYSTEM_PROMPT), *history])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    # handle_tool_errors=True turns any exception raised during a tool call (including malformed
    # MCP responses and timeouts) into an error ToolMessage the LLM can read, instead of crashing.
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)  # tool calls -> "tools", otherwise END
    graph.add_edge("tools", "agent")  # the loop-back: results return to the LLM for more reasoning
    return graph.compile(checkpointer=MemorySaver())


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content if isinstance(part, dict))


async def run_turn(graph, query: str, session_id: str) -> str:
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": RECURSION_LIMIT}
    result = await graph.ainvoke({"messages": [("user", query)]}, config=config)
    messages = result["messages"]

    # Log which tools the LLM chose this turn (only messages after the latest user message).
    turn_start = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
    tools_used = [
        call["name"]
        for m in messages[turn_start:]
        if isinstance(m, AIMessage)
        for call in m.tool_calls
    ]
    logger.info("session=%s tools_used=%s", session_id, tools_used or "none (answered directly)")

    return _message_text(messages[-1].content)