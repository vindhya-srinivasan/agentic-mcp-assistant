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

# System libraries the official Node binary links against
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 libstdc++6 && \
    rm -rf /var/lib/apt/lists/*

# Node.js from the official image: Debian's nodejs package (v20) is too old for
# readabilipy's jsdom dependency, which needs Node >= 22.22 / 24.15 / 26.
COPY --from=node:26-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:26-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx && \
    npm install -g @modelcontextprotocol/server-filesystem tavily-mcp && \
    npm cache clean --force

# The venv lives outside /root so the non-root user can read it
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

# mcp-server-fetch's readabilipy runs `npm install` on first use. Do it now, as root,
# because the non-root runtime user can't write into the venv.
RUN python -c "from readabilipy import simple_json_from_html_string; simple_json_from_html_string('<p>warmup</p>', use_readability=True)"

COPY . .
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
CMD ["python", "main.py"]