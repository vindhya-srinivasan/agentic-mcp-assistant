"""FastAPI entry point: POST /chat runs one agent turn, with memory keyed by session_id."""

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

from agent import build_graph, run_turn
from mcp_client import load_mcp_tools

load_dotenv()  # local development only; Cloud Run supplies env vars directly
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("agent-api")


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    session_id: str = Field(min_length=1)


class ChatResponse(BaseModel):
    response: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Discover MCP tools and build the graph once, so the memory checkpointer
    # lives for the whole server process and is shared across requests.
    tools, status = await load_mcp_tools()
    logger.info("MCP servers: %s", status)
    app.state.graph = build_graph(tools)
    yield


app = FastAPI(title="CSCI 599 MCP Agent", lifespan=lifespan)


@app.get("/")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        answer = await run_turn(app.state.graph, request.query, request.session_id)
    except Exception:
        # Last line of defence: never surface an unhandled 500 to the caller.
        logger.exception("Agent turn failed for session %s", request.session_id)
        answer = "Sorry, something went wrong while processing your request. Please try again."
    return ChatResponse(response=answer)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))  # Cloud Run injects PORT
    uvicorn.run(app, host="0.0.0.0", port=port)