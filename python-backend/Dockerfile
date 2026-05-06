# ========================================
# AI 爆款文章创作器 - Python 后端 Dockerfile
# ========================================
# Mermaid CLI 依赖 Node >= 22；Debian/apt 自带的 node 过旧且易触发 EBADENGINE。
# 因此在独立 Node 镜像中安装 mermaid-cli，再挂载拷贝进 Python 层（避免污染 /usr/local/bin 里的 python）。
#
# 可通过 build-arg 覆盖：PYTHON_IMAGE / NODE_IMAGE（国内见 docker-compose.mirror.yml）、NPM_CONFIG_REGISTRY（npm 源与超时）。

ARG NODE_IMAGE=node:22-bookworm-slim
ARG NPM_CONFIG_REGISTRY=https://registry.npmjs.org/
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${NODE_IMAGE} AS mermaid-cli

ARG NPM_CONFIG_REGISTRY
RUN npm config set registry "${NPM_CONFIG_REGISTRY}" \
    && npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 180000 \
    && npm install -g @mermaid-js/mermaid-cli

FROM ${PYTHON_IMAGE} AS build

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=bind,from=mermaid-cli,source=/usr/local,target=/mnt/node \
    set -eux; \
    install -m 0755 /mnt/node/bin/node /usr/local/bin/node; \
    cp -a /mnt/node/lib/node_modules /usr/local/lib/node_modules; \
    for x in npm npx mmdc; do \
      if [ -e "/mnt/node/bin/$x" ] || [ -L "/mnt/node/bin/$x" ]; then \
        cp -a "/mnt/node/bin/$x" "/usr/local/bin/$x"; \
      fi; \
    done

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

COPY app ./app

FROM ${PYTHON_IMAGE}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=bind,from=mermaid-cli,source=/usr/local,target=/mnt/node \
    set -eux; \
    install -m 0755 /mnt/node/bin/node /usr/local/bin/node; \
    cp -a /mnt/node/lib/node_modules /usr/local/lib/node_modules; \
    for x in npm npx mmdc; do \
      if [ -e "/mnt/node/bin/$x" ] || [ -L "/mnt/node/bin/$x" ]; then \
        cp -a "/mnt/node/bin/$x" "/usr/local/bin/$x"; \
      fi; \
    done

COPY --from=build /app /app

RUN groupadd -g 1000 appuser \
    && useradd -u 1000 -g appuser -m appuser \
    && chown -R appuser:appuser /app

USER appuser

ENV SERVER_HOST=0.0.0.0
ENV SERVER_PORT=8123

EXPOSE 8123

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8123/api/health/ || exit 1

CMD ["./.venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8123"]
