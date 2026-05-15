# Docker Setup Guide for Research Agent

This guide walks you through setting up and running the Research Agent using Docker.

For a copy-paste restart sequence after code or configuration changes, see
[Docker Restart Instructions](docker-restart-instructions.md).

---

## Prerequisites

Before you begin, ensure you have:

1. **Docker Desktop** installed and running
   - Download: [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
   - Verify: `docker --version`

2. **Docker Compose** (included with Docker Desktop)
   - Verify: `docker compose version`

3. **Your `.env` file configured** with at least one LLM provider API key

---

## Step-by-Step Setup

### Step 1: Open a Terminal

Open PowerShell or your preferred terminal and navigate to the project root:

```powershell
cd D:\Coding\Research-Agent
```

### Step 2: Verify Your `.env` File

Make sure your `.env` file exists and has your API keys:

```powershell
cat .env
```

You should see your API keys filled in (for example, `OPENROUTER_API_KEY=replace-with-openrouter-api-key`).

### Step 3: Build the Docker Images

Build both the backend and frontend containers:

```powershell
docker compose build
```

This will:

- Build the Python backend (FastAPI + CrewAI)
- Build the Next.js frontend
- Download base images if needed

**Expected time:** 2-5 minutes on first run.

### Step 4: Start the Containers

Launch all services:

```powershell
docker compose up -d
```

The `-d` flag runs containers in detached mode (background).

### Step 5: Verify Services Are Running

Check that all containers started successfully:

```powershell
docker compose ps
```

You should see:

| Name | Status |
|------|--------|
| research-agent-backend | running |
| research-agent-frontend | running |

### Step 6: Access the Application

- **Frontend (UI):** [http://localhost:3000](http://localhost:3000)
- **Backend API:** [http://localhost:8000](http://localhost:8000)
- **API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Useful Commands

### View Logs

```powershell
# All services
docker compose logs -f

# Backend only
docker compose logs -f backend

# Frontend only
docker compose logs -f frontend
```

### Stop Containers

```powershell
docker compose down
```

### Rebuild After Code Changes

```powershell
docker compose build --no-cache
docker compose up -d
docker compose exec backend research-agent init
docker compose exec backend research-agent health --strict
```

### Include Local Ollama (Optional)

To also run a local Ollama instance:

```powershell
docker compose --profile local-llm up -d
```

This adds an Ollama container accessible at `http://localhost:11434`.

---

## Troubleshooting

### Backend won't start

Check logs:

```powershell
docker compose logs backend
```

Common issues:

- Missing API keys in `.env`
- Port 8000 already in use (change `API_PORT` in `.env`)

### Database migrations

Alembic migrations are explicit. After building a new backend image or pulling schema changes, run:

```powershell
docker compose exec backend research-agent init
docker compose exec backend research-agent health --strict
```

The current Alembic baseline bootstraps the existing schema. Future schema changes should be represented as explicit Alembic revisions using operations such as `op.create_table`, `op.add_column`, `op.create_index`, and `op.drop_column` where appropriate. The backend still keeps startup schema sync as a compatibility fallback for older local SQLite files, but deployment should treat `research-agent init` as the migration step before serving traffic.

### Frontend shows "Cannot connect to API"

1. Make sure backend is running: `docker compose ps`
2. Check if backend is healthy: `curl http://localhost:8000/health`
3. Verify `NEXT_PUBLIC_API_URL` in `docker-compose.yml`. For this local Docker setup it should stay browser-facing as `http://localhost:8000`.

### Database issues

The SQLite database is stored in `./data/research_agent.db`. To reset:

```powershell
rm data/research_agent.db
docker compose restart backend
docker compose exec backend research-agent init
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Docker Network                         │
│  ┌─────────────────┐       ┌─────────────────────────┐  │
│  │  Frontend       │       │  Backend                │  │
│  │  (Next.js)      │──────▶│  (FastAPI + CrewAI)     │  │
│  │  Port: 3000     │       │  Port: 8000             │  │
│  └─────────────────┘       └───────────┬─────────────┘  │
│                                        │                │
│                                        ▼                │
│                            ┌───────────────────────┐    │
│                            │  ./data/ (volume)     │    │
│                            │  - research_agent.db  │    │
│                            └───────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```
