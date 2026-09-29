"""MCP client wrapper: loads server config, discovers tools per server, isolates failures."""

import asyncio
import json
import logging
import os

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

# Env vars a server needs. The server is skipped (not crashed) if any are missing.
REQUIRED_ENV = {"tavily": ["TAVILY_API_KEY"]}
DISCOVERY_TIMEOUT_SECONDS = 30


def load_connections(config_path: str) -> dict:
    """Read the server manifest and inject secrets from the environment."""
    with open(config_path) as f:
        config = json.load(f)

    connections = {}
    for name, conn in config.items():
        required = REQUIRED_ENV.get(name, [])
        missing = [var for var in required if not os.getenv(var)]
        if missing:
            logger.warning("Skipping MCP server '%s': missing %s", name, ", ".join(missing))
            continue
        if required:
            conn["env"] = {var: os.environ[var] for var in required}
        connections[name] = conn
    return connections


async def load_mcp_tools(config_path: str | None = None) -> tuple[list[BaseTool], dict[str, str]]:
    """Run tools/list against each server. Returns (tools, per-server status)."""
    config_path = config_path or os.getenv("MCP_SERVERS_CONFIG", "mcp_config.json")
    connections = load_connections(config_path)
    client = MultiServerMCPClient(connections)

    tools: list[BaseTool] = []
    status: dict[str, str] = {}
    for name in connections:
        try:
            server_tools = await asyncio.wait_for(
                client.get_tools(server_name=name), timeout=DISCOVERY_TIMEOUT_SECONDS
            )
        except Exception as exc:  # connection/transport failure: skip this server, keep the rest
            logger.error("MCP server '%s' unavailable: %r", name, exc)
            status[name] = "unavailable"
            continue

        for tool in server_tools:
            # Tool execution errors come back to the LLM as text instead of raising.
            tool.handle_tool_error = True
        tools.extend(server_tools)
        status[name] = f"ok ({len(server_tools)} tools)"
        logger.info("MCP server '%s': %d tools discovered", name, len(server_tools))

    return tools, status