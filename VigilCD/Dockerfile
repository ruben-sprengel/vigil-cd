FROM python:3.11-slim as builder

COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /bin/uv

RUN useradd -m -u 1000 vigilcd && \
    chown -R vigilcd:vigilcd /home/vigilcd

WORKDIR /home/vigilcd

COPY pyproject.toml uv.lock ./
COPY README.md ./

ENV UV_COMPILE_BYTECODE=1
RUN uv sync --frozen --no-editable

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    openssh-client \
    gnupg  \
    lsb-release \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc

RUN echo "Types: deb\n\
URIs: https://download.docker.com/linux/debian\n\
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")\n\
Components: stable\n\
Signed-By: /etc/apt/keyrings/docker.asc" > /etc/apt/sources.list.d/docker.sources

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    docker-ce-cli \
    docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /bin/uv

RUN groupadd -r docker || true && \
    useradd -m -u 1000 vigilcd && \
    usermod -aG docker vigilcd

WORKDIR /home/vigilcd

COPY --from=builder --chown=vigilcd:vigilcd /home/vigilcd/.venv /home/vigilcd/.venv
COPY --chown=vigilcd:vigilcd . .

ENV VIRTUAL_ENV=/home/vigilcd/.venv \
    PATH="/home/vigilcd/.venv/bin:$PATH"

RUN mkdir -p /home/vigilcd/.ssh && chmod 700 /home/vigilcd/.ssh && \
    ssh-keyscan -t rsa,ed25519 github.com >> /home/vigilcd/.ssh/known_hosts 2>/dev/null && \
    chmod 600 /home/vigilcd/.ssh/known_hosts

RUN mkdir -p /home/vigilcd/src/config && \
    chown -R vigilcd:vigilcd /home/vigilcd/src

RUN mkdir -p /home/vigilcd/repos && \
    chown -R vigilcd:vigilcd /home/vigilcd/repos

RUN chown -R vigilcd:vigilcd /home/vigilcd

USER vigilcd

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uv", "run", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]