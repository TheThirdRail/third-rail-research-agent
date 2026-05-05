# Step-by-Step: Running Research Agent

This guide covers all methods to set up, configure, and run the Research Agent locally and in Docker. It integrates our environment configuration and deployment steps for the hardened P2 release.

---

## Prerequisites

| Requirement | Version | Check Command |
|-------------|---------|---------------|
| Python | 3.11+ | `python --version` |
| pip | Latest | `pip --version` |
| Git | Any | `git --version` |
| Docker (optional) | 20+ | `docker --version` |
| Docker Compose (optional) | v2+ | `docker compose version` |

---

## Option 1: Local Development (Recommended)

### Step 1: Clone the Repository
```bash
git clone https://github.com/TheThirdRail/third-rail-research-agent.git
cd third-rail-research-agent
```

### Step 2: Create Virtual Environment
**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**Mac/Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -e ".[dev]"
```

### Step 4: Configure Environment & API Keys
Copy the example environment file:
```bash
cp .env.example .env
```
Open `.env` in your editor. **OpenRouter is recommended**.

```ini
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your-api-key

# Semantic Memory Configuration (P2 Hardened)
SEMANTIC_MEMORY_ENABLED=true
SEMANTIC_QUERY_EXPANSION_ENABLED=true
SEMANTIC_VECTOR_STORE=lancedb
```

### Step 5: Initialize and Test
```bash
# Initialize SQLite database, LanceDB, and run Alembic migrations
research-agent init

# Verify system health (Providers, DB, Vector Store, OCR)
research-agent health --strict

# Test LLM connection
research-agent test-llm
```

### Step 6: Start the Backend Server
```bash
uvicorn src.api.main:app --reload --port 8000
```
Access the API Docs at: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Option 2: Docker Deployment

### Step 1: Build and Start Services
```bash
docker compose up --build -d
```

### Step 2: Initialize and Verify
```bash
docker compose exec backend research-agent init
docker compose exec backend research-agent health --strict
```

---

## Advanced CLI & Observability

The hardened P2 release includes deep diagnostics and agent handoff inspection.

### Diagnostics
Inspect the retrieval lifecycle, extraction status, and relevance scoring for a specific run:
```bash
research-agent diagnostics <story_id>
```

### Agent Handoffs
Inspect the data bundles passed between agent stages:
```bash
research-agent handoff <story_id> --stage post-retrieval
research-agent handoff <story_id> --stage fact-extraction
```

### Benchmarks
Run scenario-based benchmarks to verify pipeline stability:
```bash
research-agent benchmark --live --live-limit 1 --format markdown
```

---

## Troubleshooting

### "No API key configured"
Ensure your `.env` file contains your chosen provider's key.

### "Database error"
The SQLite database is in `./data/research_agent.db` and LanceDB data is in `./data/lancedb`. To reset:
```powershell
rm -Recurse data/*
research-agent init
```

---

## Quick Reference Commands

| Action | Command |
|--------|---------|
| Initialize DB/Vector Store | `research-agent init` |
| Health check | `research-agent health --strict` |
| Diagnostics | `research-agent diagnostics <id>` |
| Handoff check | `research-agent handoff <id> --stage <stage>` |
| Live benchmark | `research-agent benchmark --live` |
| Test LLM | `research-agent test-llm` |
| Start API (dev) | `uvicorn src.api.main:app --reload` |
| Run tests | `pytest tests/ -v` |
