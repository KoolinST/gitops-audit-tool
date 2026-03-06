FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/kubectl && \
    apt-get remove -y curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --upgrade pip && \
    pip install \
    typer \
    rich \
    fastapi \
    "uvicorn[standard]" \
    sqlalchemy \
    alembic \
    asyncpg \
    httpx \
    pydantic \
    pydantic-settings \
    kubernetes \
    pygithub \
    structlog \
    prometheus-client \
    psycopg2-binary \
    greenlet

ENV PYTHONPATH=/app/src

RUN useradd --create-home --shell /bin/bash gitops
USER gitops

CMD ["python", "-m", "gitops_audit.cli.main"]
