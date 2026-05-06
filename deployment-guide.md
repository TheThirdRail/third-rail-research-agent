# Deployment Guide

Complete setup instructions for local development, Docker deployment, and LLM provider configuration.

## Local Development Setup

### Prerequisites

- **Python 3.11+** (3.12 tested)
- **pip** and **venv** (included with Python)
- **Git** for version control
- At least one LLM provider API key (see [LLM Provider Setup](#llm-provider-setup))

### Step 1: Clone and Prepare Environment

```bash
# Clone repository
git clone https://github.com/TheThirdRail/third-rail-research-agent.git
cd third-rail-research-agent

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
```

### Step 2: Install Dependencies

```bash
# Install project in development mode
pip install -e ".[dev]"

# This installs:
# - Core dependencies (crewai, fastapi, lancedb, sqlalchemy, etc.)
# - Development tools (pytest, ruff, mypy, pre-commit)
# - All extras specified in pyproject.toml
```

### Step 3: Configure Environment

```bash
# Copy example configuration
cp .env.example .env

# Edit .env and add required settings:
# 1. Set LLM_PROVIDER (default: openrouter)
# 2. Add at least one API key (OPENROUTER_API_KEY recommended)
# 3. Optional: Configure semantic memory, source gathering policies
```

**Minimal .env for local development:**

```env
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO
PYTHONIOENCODING=utf-8

LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here

DATABASE_URL=sqlite:///data/research_agent.db
SEMANTIC_MEMORY_ENABLED=false
```

### Step 4: Initialize Database

```bash
# Create database and run migrations
research-agent init

# This creates:
# - data/research_agent.db (SQLite database)
# - Required tables (Story, Source, Analysis, VideoPerformance)
# - Initial schema version
```

### Step 5: Verify System Health

```bash
# Run health check with strict validation
research-agent health --strict

# Output should show:
# ✓ Database connection: OK
# ✓ LLM provider connectivity: OK
# ✓ Configuration validation: OK
# ✓ Required dependencies: OK
```

### Step 6: Start Services

**Terminal 1 — Backend (FastAPI):**

```bash
# With virtual environment activated
uvicorn src.api.main:app --reload

# API available at: http://localhost:8000
# OpenAPI docs at: http://localhost:8000/docs
```

**Terminal 2 — Frontend (Next.js):**

```bash
# Navigate to web directory
cd web

# Install dependencies (first time only)
npm install

# Start development server
npm run dev

# UI available at: http://localhost:3000
```

**Verify both services:**

```bash
# In a third terminal
curl http://localhost:8000/health      # Backend health
curl http://localhost:3000              # Frontend homepage
```

---

## Docker Deployment

### Prerequisites

- **Docker** (20.10+)
- **Docker Compose** (2.0+)
- Configured `.env` file with API keys

### Quick Start

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Build and start all services
docker compose up --build

# Services:
# - Backend: http://localhost:8000
# - Frontend: http://localhost:3000
# - API docs: http://localhost:8000/docs
```

### Service Architecture

**backend** — FastAPI + CrewAI agents
- Port: 8000
- Volumes: `./data` (persistent database), `./config` (read-only configuration)
- Environment: All LLM provider keys, database URL, app settings
- Health: `GET /health` endpoint checked every 30s

**frontend** — Next.js web UI
- Port: 3000
- Depends on: backend service
- Build arg: `NEXT_PUBLIC_API_URL=http://localhost:8000`

**ollama** (optional) — Local LLM runtime
- Port: 11434
- Profile: `local-llm` (activated with `--profile local-llm`)
- Volume: `ollama-data` (persistent model storage)

### Common Docker Commands

```bash
# Start all services
docker compose up --build

# Start with local LLM (Ollama) included
docker compose --profile local-llm up --build

# View logs
docker compose logs -f backend          # Backend logs only
docker compose logs -f                  # All services

# Stop services
docker compose down

# Stop and remove data volumes
docker compose down -v

# Rebuild after code changes
docker compose up --build

# Run migrations in existing container
docker compose exec backend research-agent init
```

### Environment Configuration in Docker

The `docker-compose.yml` passes `.env` variables to the backend service. Key settings:

| Variable | Purpose | Docker Value |
|----------|---------|--------------|
| `LLM_PROVIDER` | Default LLM | Passed from .env |
| `OPENROUTER_API_KEY` | OpenRouter key | Passed from .env |
| `DATABASE_URL` | SQLite path | `sqlite:///data/research_agent.db` |
| `OLLAMA_BASE_URL` | Ollama endpoint | `http://ollama:11434` (if using local LLM) |
| `LOG_LEVEL` | Verbosity | Passed from .env |

**Note:** If using LM Studio from the host machine, set:
```env
LM_STUDIO_API_BASE=http://host.docker.internal:1234/v1
```

### Production Deployment Notes

- **Database:** SQLite in `./data` is suitable for single-instance deployments. For multi-instance setups, migrate to PostgreSQL.
- **Volumes:** Bind mounts (`./data`, `./config`) require consistent paths across hosts.
- **Health checks:** Frontend has no built-in health endpoint; add an external health monitor if needed.
- **Logs:** Container logs are accessible via `docker logs` or `docker compose logs`; for persistent logging, configure volume mount or external logging driver.

---

## LLM Provider Setup

Choose **one primary provider** and optional fallbacks. OpenRouter is recommended for free tier access to many models.

### OpenRouter (Recommended)

**Why:** Free tier includes Llama 4, DeepSeek, Gemma, and others. No rate limiting at tier-1 use levels.

**Setup:**

1. Visit [openrouter.ai](https://openrouter.ai/)
2. Sign up / log in
3. Navigate to **Keys** → **Create Key**
4. Copy API key
5. Add to `.env`:
   ```env
   LLM_PROVIDER=openrouter
   OPENROUTER_API_KEY=your_openrouter_api_key_here
   ```

**Model selection (UI or env var):**
- Default: System chooses best available model
- Override: Set `SELECTED_MODEL=meta-llama/llama-2-70b-chat`

**Rate limits:** Free tier: ~100 requests/hour. For higher volume, upgrade account or use local fallback.

### Anthropic (Claude)

**Setup:**

1. Visit [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
2. Create API key
3. Add to `.env`:
   ```env
   LLM_PROVIDER=anthropic
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

**Models available:** Claude 3 (Opus, Sonnet, Haiku)

### OpenAI

**Setup:**

1. Visit [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Create API key
3. Add to `.env`:
   ```env
   LLM_PROVIDER=openai
   OPENAI_API_KEY=your_openai_api_key_here
   ```

**Optional:** Custom endpoint for local bridges:
```env
OPENAI_BASE_URL=http://localhost:8000/v1
```

### Google Gemini

**Setup:**

1. Visit [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Create API key
3. Add to `.env`:
   ```env
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

### Groq

**Setup:**

1. Visit [console.groq.com/keys](https://console.groq.com/keys)
2. Create API key
3. Add to `.env`:
   ```env
   LLM_PROVIDER=groq
   GROQ_API_KEY=your_groq_api_key_here
   ```

**Note:** Groq has rate limits (~30 requests/minute on free tier). Excellent for local testing.

### Other Providers

**Cerebras:**
```env
LLM_PROVIDER=cerebras
CEREBRAS_API_KEY=your_cerebras_api_key_here
```

**SambaNova:**
```env
LLM_PROVIDER=sambanova
SAMBANOVA_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Mistral:**
```env
LLM_PROVIDER=mistral
MISTRAL_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**xAI (Grok):**
```env
LLM_PROVIDER=lmstudio
XAI_API_KEY=your_xai_api_key_here
```

### Local / Offline Options

#### Ollama (Recommended for Local)

**Setup:**

1. Install [Ollama](https://ollama.ai)
2. Pull a model: `ollama pull llama2` (or `llama2-70b`, `mistral`, etc.)
3. Ollama runs on `http://localhost:11434` by default
4. Add to `.env`:
   ```env
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   ```

**Docker variant:**
```bash
docker compose --profile local-llm up
# Ollama service will auto-download models on first start
```

**Model selection:**
```env
SELECTED_MODEL=llama2-70b
```

#### LM Studio (Alternative Local)

**Setup:**

1. Install [LM Studio](https://lmstudio.ai/)
2. Load a model in LM Studio UI
3. Start server (typically on `http://localhost:1234/v1`)
4. Add to `.env`:
   ```env
   LLM_PROVIDER=openai
   OPENAI_BASE_URL=http://localhost:1234/v1
   OPENAI_API_KEY=lm-studio
   ```

**Docker:** If backend is in Docker:
```env
OPENAI_BASE_URL=http://host.docker.internal:1234/v1
LM_STUDIO_FALLBACK_ENABLED=true
LM_STUDIO_FALLBACK_MODEL=qwen2.5-7b-instruct
```

---

## Configuration Deep Dive

### Application Settings

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_ENV` | `development` | Environment mode (development/production) |
| `DEBUG` | `true` | Enable debug logging and verbose output |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARN, ERROR) |
| `PYTHONIOENCODING` | `utf-8` | Force UTF-8 encoding (critical on Windows) |

### API Settings

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_HOST` | `0.0.0.0` | Bind address for FastAPI backend |
| `API_PORT` | `8000` | Port for FastAPI backend |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Frontend API endpoint (baked at build) |

### Database

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite:///data/research_agent.db` | SQLite path (relative to project root) |

**Notes:**
- SQLite works well for single-user local development.
- For multi-instance or production, use PostgreSQL: `postgresql://user:pass@host:5432/research_agent`
- Database file is created automatically on first `research-agent init`.

### Source Gathering Policy

Control how sources are selected and balanced across political spectrum.

| Variable | Default | Purpose |
|----------|---------|---------|
| `CANDIDATE_PROBE_LIMIT` | `15` | Max sources to initially probe |
| `RETAINED_SOURCE_MIN` | `3` | Minimum sources in final report |
| `RETAINED_SOURCE_MAX` | `5` | Maximum sources in final report |
| `STRICT_BUCKET_ENFORCEMENT` | `true` | Enforce left/center/right balance |
| `REQUIRED_BUCKET_GROUPS` | `left_side,right_side` | Buckets that must have >= 1 source |
| `MAX_PER_BUCKET_GROUP` | `2` | Max sources per political group |
| `EXACT_CENTER_PREFERRED` | `true` | Prefer neutral sources if available |
| `SEARCH_TIME_WINDOW_DAYS` | `7` | How recent stories must be |

**Example: Enforce 2L / 1C / 2R distribution:**
```env
STRICT_BUCKET_ENFORCEMENT=true
REQUIRED_BUCKET_GROUPS=left_side,right_side
MAX_PER_BUCKET_GROUP=2
EXACT_CENTER_PREFERRED=true
```

### Semantic Search (Advanced)

| Variable | Default | Purpose |
|----------|---------|---------|
| `SEMANTIC_MEMORY_ENABLED` | `false` | Enable LanceDB vector store |
| `SEMANTIC_QUERY_EXPANSION_ENABLED` | `false` | Expand queries with LLM |
| `SEMANTIC_CANDIDATE_SCORING_ENABLED` | `false` | Score sources semantically |
| `SEMANTIC_TOP_K` | `4` | Results per semantic query |
| `EMBEDDING_PROVIDER` | `fake` | Embedding service (fake/lmstudio/ollama) |
| `EMBEDDING_MODEL` | `fake-hash-v1` | Embedding model ID |

**To enable semantic memory:**
1. Set `SEMANTIC_MEMORY_ENABLED=true`
2. Load an embeddings model in LM Studio
3. Set `EMBEDDING_PROVIDER=lmstudio` and `EMBEDDING_MODEL=<model-id>`
4. Restart backend

---

## Troubleshooting Deployment Issues

### Database Initialization Fails

**Error:** `database locked` or `unable to open database file`

**Solution:**
1. Ensure `data/` directory exists and is writable: `mkdir -p data`
2. Check for stale database locks: `rm data/research_agent.db.lock` (if present)
3. Run initialization: `research-agent init`
4. Verify: `research-agent health --strict`

### LLM Provider Connection Fails

**Error:** `Connection refused` or `Invalid API key`

**Solution:**
1. Verify API key is in `.env` without quotes:
   ```env
   OPENROUTER_API_KEY=your_openrouter_api_key_here  # Correct
   # OPENROUTER_API_KEY="sk-or-v1-xxxxx"  # Wrong (includes quotes)
   ```
2. Test provider directly:
   ```bash
   curl -H "Authorization: Bearer $OPENROUTER_API_KEY" \
     https://openrouter.ai/api/v1/models
   ```
3. Check firewall/proxy if using corporate network
4. Verify environment variable is loaded:
   ```bash
   echo $OPENROUTER_API_KEY  # Should print your key
   ```

### FastAPI Backend Won't Start

**Error:** `Port 8000 already in use` or `uvicorn: command not found`

**Solution:**
1. Check if another process is using port 8000:
   ```bash
   lsof -i :8000  # macOS/Linux
   netstat -ano | findstr :8000  # Windows
   ```
2. Kill existing process or use different port:
   ```bash
   uvicorn src.api.main:app --port 8001 --reload
   ```
3. Verify virtual environment is activated (shows `(.venv)` in prompt)
4. Reinstall dependencies: `pip install -e ".[dev]"`

### Frontend Can't Reach Backend

**Error:** `Failed to fetch from http://localhost:8000` (in browser console)

**Solution:**
1. Verify backend is running: `curl http://localhost:8000/health`
2. Check `NEXT_PUBLIC_API_URL` in `.env` or Next.js `.env.local`
3. In Docker: Frontend must reach backend via service name:
   ```env
   NEXT_PUBLIC_API_URL=http://backend:8000  # Inside Docker Compose
   ```
4. For local development, use `http://localhost:8000`

### Docker Container Exits Immediately

**Error:** `docker compose up` shows container starting then exiting

**Solution:**
1. Check logs: `docker compose logs backend`
2. Common causes:
   - Missing environment variables: Verify `.env` is loaded
   - Database initialization failed: Run `docker compose exec backend research-agent init`
   - Port already in use: Stop other containers or map to different port
3. Rebuild image: `docker compose up --build`

### Health Check Fails

**Error:** `research-agent health --strict` returns errors

**Solution:**
1. Run without `--strict` for more details: `research-agent health`
2. Check individual components:
   - Database: `sqlite3 data/research_agent.db ".tables"`
   - LLM provider: Verify API key and network connectivity
   - Dependencies: `pip list | grep crewai`
3. Review logs: `tail -50 data/research_agent.log` (if logging enabled)

### Semantic Memory Issues

**Error:** `LanceDB initialization failed` or `Embedding provider unreachable`

**Solution:**
1. Semantic memory is optional; disable if not needed:
   ```env
   SEMANTIC_MEMORY_ENABLED=false
   SEMANTIC_QUERY_EXPANSION_ENABLED=false
   ```
2. If using LM Studio embeddings, verify:
   - LM Studio is running and has an embeddings model loaded
   - `EMBEDDING_PROVIDER=lmstudio` is set
   - `EMBEDDING_MODEL` matches loaded model ID
3. Check LM Studio server: `curl http://localhost:1234/v1/models`

### Performance Issues

**Slow startup:**
- First startup downloads models and builds embeddings; subsequent runs are faster
- Disable semantic memory if not needed: `SEMANTIC_MEMORY_ENABLED=false`

**Slow analysis:**
- Check LLM provider response times: Add `LOG_LEVEL=DEBUG` and review logs
- Reduce source candidate limit: `CANDIDATE_PROBE_LIMIT=10` (lower = faster)
- Use faster local model (Ollama): `ollama pull mistral` (smaller than llama2-70b)

---

## Production Deployment Checklist

Before deploying to production:

- [ ] Database: Migrate to PostgreSQL or ensure SQLite backup strategy
- [ ] Secrets: Use environment variables or secret manager (not hardcoded in `.env`)
- [ ] Logging: Configure persistent log storage or external logging service
- [ ] Monitoring: Set up health check and alerting (e.g., Uptime Robot)
- [ ] Backups: Regular database snapshots and configuration backups
- [ ] SSL/TLS: Use HTTPS (e.g., Nginx reverse proxy with Let's Encrypt)
- [ ] Rate Limiting: Add request rate limiting to FastAPI
- [ ] CORS: Configure `CORS_ORIGINS` for allowed frontend domains
- [ ] Error Handling: Set up error tracking (e.g., Sentry)
- [ ] Resource Limits: Set CPU/memory limits in Docker Compose or orchestration platform

---

## Support

For deployment issues not covered here:

- **Logs:** `docker compose logs backend` or `uvicorn` console output
- **Health Check:** `research-agent health --strict` (comprehensive validation)
- **Diagnostics:** `research-agent diagnostics <story_id>` (post-analysis troubleshooting)
- **GitHub Issues:** [Report issues on GitHub](https://github.com/TheThirdRail/third-rail-research-agent/issues)
