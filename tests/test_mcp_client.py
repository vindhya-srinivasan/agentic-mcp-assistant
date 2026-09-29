import asyncio
import json

from dotenv import load_dotenv

from mcp_client import load_mcp_tools

load_dotenv()


def _tool(tools, name):
    return next(t for t in tools if t.name == name)


def test_discovers_filesystem_and_fetch():
    tools, status = asyncio.run(load_mcp_tools("mcp_config.json"))
    names = {t.name for t in tools}
    assert status["filesystem"].startswith("ok")
    assert status["fetch"].startswith("ok")
    assert {"read_text_file", "fetch"} <= names


def test_filesystem_tool_call():
    tools, _ = asyncio.run(load_mcp_tools("mcp_config.json"))
    result = asyncio.run(_tool(tools, "read_text_file").ainvoke({"path": "sample.txt"}))
    assert "Hello" in str(result)


def test_tool_execution_error_does_not_raise():
    tools, _ = asyncio.run(load_mcp_tools("mcp_config.json"))
    result = asyncio.run(_tool(tools, "read_text_file").ainvoke({"path": "missing.txt"}))
    assert "no such file" in str(result).lower()


def test_unavailable_server_is_skipped(tmp_path):
    config = {
        "broken": {"command": "definitely-not-a-real-binary", "args": [], "transport": "stdio"},
        "fetch": {"command": "python", "args": ["-m", "mcp_server_fetch"], "transport": "stdio"},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))

    tools, status = asyncio.run(load_mcp_tools(str(path)))
    assert status["broken"] == "unavailable"
    assert status["fetch"].startswith("ok")
    assert any(t.name == "fetch" for t in tools)