FROM python:3.12-slim

WORKDIR /app

RUN useradd --create-home --uid 10001 mcp \
 && mkdir -p /home/mcp/.neo-recall \
 && chown -R mcp:mcp /home/mcp /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY probe.py ./

RUN pip install --no-cache-dir -e . \
 && chown -R mcp:mcp /app

USER mcp

# Credentials via env (keyring unavailable in many containers):
#   NEOSAPIEN_FIREBASE_API_KEY
#   NEOSAPIEN_REFRESH_TOKEN
ENV NEOSAPIEN_CACHE_PATH=/home/mcp/.neo-recall/memories.db

ENTRYPOINT ["neosapien-mcp"]
