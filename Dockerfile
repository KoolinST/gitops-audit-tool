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

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN echo '#!/usr/bin/env python\nimport sys\nfrom gitops_audit.cli.main import app\nsys.exit(app())' > /usr/local/bin/gitops-audit && \
    chmod +x /usr/local/bin/gitops-audit

ENV PYTHONPATH=/app/src

RUN useradd --create-home --shell /bin/bash gitops
USER gitops

CMD ["python", "-m", "gitops_audit.cli.main"]
