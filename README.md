# GitOps Audit Trail & Rollback System

> Automated deployment tracking, metrics correlation, and one-command rollback for Kubernetes/ArgoCD environments.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)](https://postgresql.org)
[![ArgoCD](https://img.shields.io/badge/ArgoCD-2.x-orange.svg)](https://argoproj.github.io/argo-cd/)
[![Helm](https://img.shields.io/badge/Helm-3.x-blue.svg)](https://helm.sh)
[![CI](https://github.com/KoolinST/gitops-audit-tool/actions/workflows/ci.yml/badge.svg)](https://github.com/KoolinST/gitops-audit-tool/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## The Problem

When a GitOps deployment causes a production incident, engineers face:

- 20–30 minutes manually correlating deployments with Grafana + ArgoCD + Git
- No automatic detection of metric degradation after a deploy
- Uncertainty about which commit to roll back to
- No audit trail for post-mortems or compliance

## The Solution

`gitops-audit` is a Kubernetes operator that watches ArgoCD for deployment events, automatically captures Prometheus metrics before and after each deploy, detects anomalies, and enables instant rollback — all from the CLI.
```
┌──────────────┐     ┌───────────────┐     ┌───────────────┐
│    ArgoCD    │────▶│    Watcher    │────▶│  PostgreSQL   │
│  (syncs app) │     │  (captures    │     │  (audit trail)│
└──────────────┘     │   metrics)    │     └───────────────┘
                     └──────┬────────┘
                            │
                  ┌─────────▼──────────┐
                  │  MetricsAnalyzer   │
                  │  (detects issues)  │
                  └─────────┬──────────┘
                            │
               ┌────────────▼───────────┐
               │   Slack Alert / CLI    │
               │  gitops-audit rollback │
               └────────────────────────┘
```

---

## Features

- **Automatic deployment tracking** — watches ArgoCD Application CRDs in real time
- **Before/after metrics** — captures CPU, memory, error rate, latency from Prometheus 30s after each deploy
- **Anomaly detection** — flags error rate spikes, latency increases, CPU/memory surges
- **One-command rollback** — triggers ArgoCD sync to any previous commit with full audit trail
- **Slack alerts** — notifies on degraded deployments with rollback command included
- **GitHub integration** — enriches deployments with commit author, message, and PR approval info
- **REST API** — FastAPI server with Swagger docs for programmatic access
- **Full audit trail** — every deployment, rollback, and metric snapshot stored in PostgreSQL

---

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry
- Docker + Docker Compose
- Kind + kubectl
- ArgoCD installed in cluster

### Local Development
```bash
git clone https://github.com/KoolinST/gitops-audit
cd gitops-audit

# Install dependencies
poetry install

# Copy and configure environment
cp .env.example .env

# Start PostgreSQL
docker-compose up -d postgres

# Run database migrations
poetry run alembic upgrade head

# Start the watcher
poetry run gitops-audit watcher

# Start the API (separate terminal)
poetry run gitops-audit api
```

### Deploy to Kubernetes with Helm
```bash
# Install into your cluster
helm install gitops-audit ./charts/gitops-audit \
  --namespace gitops-audit \
  --create-namespace \
  --set secrets.githubToken=your_token \
  --set secrets.slackWebhookUrl=https://hooks.slack.com/... \
  --set secrets.databaseUrl=postgresql+asyncpg://user:pass@host:5432/gitops_audit \
  --set config.prometheusUrl=http://prometheus-operated.monitoring:9090

# Check status
kubectl get pods -n gitops-audit

# Access the API
kubectl port-forward svc/gitops-audit-api 8000:8000 -n gitops-audit
```

### Environment Variables

Create a `.env` file from the example:
```env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/gitops_audit
PROMETHEUS_URL=http://localhost:9090
GITHUB_TOKEN=your_github_token        # optional — enables commit/PR metadata
SLACK_WEBHOOK_URL=https://hooks.slack.com/...  # optional — enables alerts
LOG_LEVEL=INFO
```

---

## CLI Commands

### `watcher` — Start the deployment watcher
```bash
poetry run gitops-audit watcher
```
Watches ArgoCD for sync events, captures metrics, detects anomalies, and sends Slack alerts.

---

### `api` — Start the REST API server
```bash
poetry run gitops-audit api
# API docs available at http://localhost:8000/docs
```

---

### `history` — View deployment history
```bash
# All deployments
poetry run gitops-audit history

# Filter by app
poetry run gitops-audit history guestbook

# Limit results
poetry run gitops-audit history --limit 5
```
```
╭────┬───────────┬─────────────────────┬──────────┬──────────────╮
│ ID │ App Name  │ Deployed At         │ Commit   │ Health       │
├────┼───────────┼─────────────────────┼──────────┼──────────────┤
│ 21 │ guestbook │ 2026-03-03 08:56:19 │ 723b86e0 │ ● Healthy    │
│ 18 │ guestbook │ 2026-03-03 08:42:12 │ 723b86e0 │ ● Healthy    │
╰────┴───────────┴─────────────────────┴──────────┴──────────────╯
```

---

### `show` — Detailed deployment info
```bash
poetry run gitops-audit show 21
```
```
╭─────────────── Deployment #21: guestbook ───────────────╮
│        ID:  21                                           │
│  App Name:  guestbook                                    │
│ Namespace:  default                                      │
│    Commit:  723b86e01bea11dcf72316cb172868fcbf05d69e     │
│    Author:  Michael Crenshaw                             │
│   Message:  fix: update guestbook image                  │
│  PR Number: #443                                         │
│ Approved By: user1, user2                                │
╰──────────────────────────────────────────────────────────╯
```

---

### `correlate` — Analyze deployment metrics impact
```bash
poetry run gitops-audit correlate 21
```
```
╭──────────────┬──────────┬──────────┬────────╮
│ Metric       │   Before │    After │ Change │
├──────────────┼──────────┼──────────┼────────┤
│ Cpu Usage    │   0.0002 │   0.0002 │  -3.5% │
│ Memory Usage │ 24.68 MB │ 24.68 MB │     0% │
╰──────────────┴──────────┴──────────┴────────╯
✓ No significant issues detected
```

---

### `rollback` — Roll back to a previous deployment
```bash
# With confirmation prompt
poetry run gitops-audit rollback 21

# With reason and skip confirmation
poetry run gitops-audit rollback 21 --reason "High error rate" --yes
```
```
╭──────────────── ⚠ Rolling back to Deployment #21 ────────────────╮
│       App:  guestbook                                             │
│ Namespace:  default                                               │
│    Commit:  723b86e0                                              │
╰───────────────────────────────────────────────────────────────────╯
→ Triggering rollback for guestbook...
✓ Rollback triggered successfully
```

Rollback is recorded in the `rollbacks` table for audit trail.

---

### `apps` — List all tracked applications
```bash
poetry run gitops-audit apps
```
```
╭───────────────────────────┬───────────────────┬──────────────────╮
│ App Name                  │ Total Deployments │ Last Deployed    │
├───────────────────────────┼───────────────────┼──────────────────┤
│ guestbook                 │                 7 │ 2026-03-03 08:56 │
│ nginx-demo                │                 3 │ 2026-03-03 08:23 │
╰───────────────────────────┴───────────────────┴──────────────────╯
```

---

## REST API

Start the API server and open `http://localhost:8000/docs` for interactive Swagger documentation.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | System health check |
| GET | `/api/deployments` | List deployments (filter by app, limit) |
| GET | `/api/deployments/{id}` | Deployment details |
| GET | `/api/deployments/{id}/metrics` | Before/after metrics analysis |
| GET | `/api/deployments/{id}/rollbacks` | Rollback history |
| GET | `/api/apps` | List all tracked applications |
| GET | `/api/apps/{name}/deployments` | App deployment history |

---

## Architecture

### Components

**Watcher** (`watcher/argocd_watcher.py`)
Kubernetes controller that watches ArgoCD Application CRDs. On each `Synced + Healthy` event it captures metrics, fetches Git metadata, records the deployment, waits 30s, captures after-metrics, runs anomaly analysis, and sends Slack alerts if needed. Uses per-app async locks to prevent duplicate recordings under concurrent events.

**MetricsAnalyzer** (`analysis/metrics_analyzer.py`)
Compares before/after metric snapshots and flags significant changes using configurable thresholds: 100% error rate increase, 50% latency increase, 30% request rate drop, 100% CPU increase, 50% memory increase.

**PrometheusClient** (`integrations/prometheus.py`)
Queries CPU, memory, error rate, request rate, and latency (P50/P95) using PromQL with pod-based label matching compatible with cAdvisor and kube-state-metrics.

**GitHubClient** (`integrations/github.py`)
Fetches commit author, message, and associated PR approval info for each deployment.

**SlackClient** (`integrations/slack.py`)
Sends formatted Slack alerts for degraded deployments (warning/critical) and success notifications for healthy ones. Gracefully disabled when no webhook is configured.

### Database Schema
```sql
deployments       -- ArgoCD sync events with git metadata
git_commits       -- Commit author, message, PR number, approvers
metrics_snapshots -- Before/after Prometheus metrics per deployment
rollbacks         -- Rollback history with reason and success status
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| CLI | Typer + Rich |
| API | FastAPI + uvicorn |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL 15 |
| Migrations | Alembic |
| Kubernetes | Kind + ArgoCD |
| Packaging | Helm 3 |
| Metrics | Prometheus + cAdvisor |
| Git | GitHub API (PyGithub) |
| Alerts | Slack Incoming Webhooks |
| Logging | structlog |
| HTTP | httpx (async) |

---

## Project Structure
```
gitops-audit/
├── src/
│   └── gitops_audit/
│       ├── analysis/
│       │   └── metrics_analyzer.py   # Anomaly detection
│       ├── api/
│       │   ├── main.py               # FastAPI application
│       │   └── schemas.py            # Pydantic response models
│       ├── cli/
│       │   ├── commands/
│       │   │   ├── apps.py           # List tracked apps
│       │   │   ├── correlate.py      # Metrics comparison
│       │   │   ├── history.py        # Deployment history
│       │   │   ├── rollback.py       # Rollback command
│       │   │   └── show.py           # Deployment details
│       │   └── main.py               # CLI entry point
│       ├── config/
│       │   ├── logging.py            # structlog setup
│       │   └── settings.py           # Pydantic settings
│       ├── database/
│       │   ├── connection.py         # Async SQLAlchemy engine
│       │   ├── models.py             # ORM models
│       │   └── queries.py            # Reusable queries
│       ├── integrations/
│       │   ├── github.py             # GitHub API client
│       │   ├── prometheus.py         # Prometheus client
│       │   └── slack.py              # Slack webhook client
│       └── watcher/
│           └── argocd_watcher.py     # Kubernetes controller
├── charts/
│   └── gitops-audit/                 # Helm chart
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│           ├── deployment-watcher.yaml
│           ├── deployment-api.yaml
│           ├── service-api.yaml
│           ├── configmap.yaml
│           ├── secret.yaml
│           ├── serviceaccount.yaml
│           └── rbac.yaml
├── alembic/                          # Database migrations
├── tests/
│   ├── test_database.py
│   └── test_suite.py
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── pyproject.toml
```

---

## Development
```bash
# Run tests
poetry run pytest

# Linting
poetry run ruff check .
poetry run black .

# Type checking
poetry run mypy src
```

---

## Roadmap

- [ ] `gitops-audit doctor` — verify connectivity to Prometheus, ArgoCD, and DB
- [ ] GitHub Actions CI pipeline
- [ ] PagerDuty integration

---

## License

MIT

---

*Built to demonstrate practical DevOps/platform engineering skills — Kubernetes operators, GitOps workflows, observability, and incident response automation.*
