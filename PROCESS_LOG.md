# Process Log: CSCI 599 Assignment 1

## 1. AI tools used

- **Claude** (Anthropic, model `claude-opus-5-5`, via the Claude app). I used it to plan the setup steps, generate most of the Python code and the Dockerfile, debug build and runtime errors, draft the README and its diagrams, and write a first draft of this log, which I then edited.
- I didn't use any other AI tools.

## 2. Development narrative

I started with setup, which took longer than I expected. My NVIDIA login put me in an organization where I couldn't create API keys, so I had to make my own. On GCP, I couldn't link billing until I realized I hadn't redeemed the education credit yet. I also lost time because my venv was quietly running Python 3.10 instead of 3.14, which I only noticed in a pytest header.

Before writing agent code, I tested each MCP server alone in the MCP Inspector. Two of my early failures were just empty files: `requirements.txt` and `mcp_config.json` had been created but never filled in.

The agent itself (LangGraph graph, MemorySaver, FastAPI) came together fairly quickly. The tests then failed with "Event loop is closed", because each test used `asyncio.run()` and the OpenAI client reused a connection tied to an old loop. Sharing one loop fixed it.

Deployment caused the hardest bugs. A fetch request to lipsum.com hung, and afterwards that session always errored, because the interrupted turn left a tool call with no result in memory. I asked Claude why fetch worked for example.com but not lipsum.com. The answer was that my agent had no timeouts, so I added limits on tool and LLM calls. Then fetch failed with "npm install exit status 243". The prompt that finally cracked it was pasting that exact error and asking why fetch failed only in the container. It turned out readabilipy runs `npm install` on first use, and my non-root container user couldn't write to the venv. Moving that step into the build exposed the real problem: Debian's Node 20 is too old for jsdom, so I switched to Node 26 from the official Node image.

## 3. Verification narrative

- **Automated tests.** I wrote 8 pytest tests that hit the real MCP servers and the real NVIDIA model, not mocks. They cover tool discovery, a real `tools/call`, a missing file, an unavailable server, picking the filesystem tool, answering a math question with no tool, session-scoped memory, and "What did I ask you last?".
- **Watching the protocol.** Before writing any agent code, I watched the `initialize`, `tools/list` and `tools/call` messages for each server in the MCP Inspector.
- **Breaking things on purpose.** I pointed the config at a server binary that doesn't exist, and it was skipped while the other servers still loaded. I asked for a file that doesn't exist, and the agent reported the error instead of crashing. I ran without the Tavily key, and that server was skipped with a warning.
- **Three environments.** I ran the same checks locally, in Docker and on Cloud Run. Several bugs only showed up in the container, so I stopped trusting local results on their own.
- **Checking tool selection.** I added a log line that records which tools the model picked on each turn. From the Cloud Run logs:

```
2026-10-12 02:16:39,557 INFO agent: session=grader-1 tools_used=none (answered directly)
2026-10-12 02:58:42,554 INFO agent: session=log-file tools_used=['list_directory', 'read_text_file']
2026-10-12 02:59:18,451 INFO agent: session=log-search tools_used=['tavily_search', 'fetch']
2026-10-12 03:00:10,680 INFO agent: session=log-chain tools_used=['tavily_search', 'fetch', 'fetch', 'tavily_search', 'fetch', 'fetch', 'write_file']
INFO:     169.254.169.126:17950 - "POST /chat HTTP/1.1" 422 Unprocessable Content
```

The general-knowledge question used no tool. For "What does sample.txt say?" the model listed the workspace first, then read the file. For the news question it searched with Tavily, then fetched a result page. The chained request used all three servers and went around the tool loop several times: it searched, fetched two pages, searched again, fetched two more, and then wrote the file. I expected fewer calls, but it showed the loop-back working, with the model checking after each result whether it had enough. The 422 was a request I sent with a missing field, which FastAPI rejected before it reached the agent.

- **Memory on the live URL.** The same `session_id` remembered my name across turns, and "What did I ask you last?" returned my actual previous question. A different `session_id` remembered neither.
- **Local run.** I also ran the server locally, with a second terminal sending requests. "What is CAP theorem?" logged `tools_used=none`, so the model answered from its own knowledge instead of forcing a search.

## 4. What I learned

The AI could suggest fixes, but it couldn't see my machine or the container. On the readabilipy and Node bug, I had to run things in the container myself and bring back the real error before the cause was clear. I also learned to test where the code actually runs, not just locally, and that timeouts turn a mysterious hang into an error I can actually read.
