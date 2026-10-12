# Build stage: install Python dependencies into a self-contained venv
FROM python:3.14-slim AS build
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.14-slim
WORKDIR /app

# Node.js runtime for the Node-based MCP servers, pre-installed globally so cold
# starts don't download them via npx
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && \
    rm -rf /var/lib/apt/lists/* && \
    npm install -g @modelcontextprotocol/server-filesystem tavily-mcp && \
    npm cache clean --force

# The venv lives outside /root so the non-root user can read it
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

COPY . .
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
CMD ["python", "main.py"]