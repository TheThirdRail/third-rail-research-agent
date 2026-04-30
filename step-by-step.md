# Step-by-Step: Running Research Agent

This guide covers all methods to set up, configure, and run the Research Agent locally and in Docker. It integrates our environment configuration and deployment steps.

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
Open `.env` in your editor. The crucial setting is your `LLM_PROVIDER` and corresponding API key. **OpenRouter is recommended** as it provides access to many models using a single key.

```ini
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=mock-or-v1-xxxxxxxx

# Optional Semantic Memory Configuration
SEMANTIC_MEMORY_ENABLED=true
SEMANTIC_QUERY_EXPANSION_ENABLED=true
VECTOR_STORE_PROVIDER=lancedb
```

*Other valid `LLM_PROVIDER` options: `openai`, `anthropic`, `gemini`, `groq`, `cerebras`, `sambanova`, `mistral`, `ollama`.*

> **Note**: Model Selection is done via the UI or CLI parameters. You do not need to set `SELECTED_MODEL` or `ANALYSIS_MODEL` in your `.env` manually unless you specifically want to override defaults.

### Step 5: Initialize and Test
```bash
# Initialize SQLite database (creates data/research_agent.db)
research-agent init

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

### Step 1: Clone and Configure
Follow Steps 1 and 4 from above to clone the repository and configure your `.env` file with the necessary API keys.

### Step 2: Build and Start Services
Run the following to build the images and run the containers in detached mode:
```powershell
docker compose up --build -d
```

This spins up the following network:
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **Frontend UI**: [http://localhost:3000](http://localhost:3000) *(in development)*

### Step 3: Verify Services
```powershell
docker compose ps
docker compose logs -f backend
```
Check health: `curl http://localhost:8000/health`

### Step 4: Using with Local Ollama
To run completely offline or use free local inference, start the `local-llm` profile:
```powershell
docker compose --profile local-llm up --build -d
```
This adds the `ollama` container at `http://localhost:11434`. Pull a model into the container:
```powershell
docker exec research-agent-ollama ollama pull llama3
```
Update your `.env` to point to it:
```ini
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
```

### Step 5: Stop Containers
```powershell
docker compose down
```

---

## Option 3: API-Only Mode

Run just the backend API without Docker or Frontend components:
```bash
# Terminal 1: Start API
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Test endpoints
curl http://localhost:8000/api/config
curl http://localhost:8000/api/models
```

---

## Optional: Codex OAuth Testing (Advanced)

For local development involving a locally authenticated Codex/OAuth workflow. *Do not use in production or expose publicly.*

### Enabling Bridge Mode:
1. Set the following in your `.env`:
   ```ini
   LLM_PROVIDER=openai
   OPENAI_BASE_URL=http://host.docker.internal:8787/v1
   OPENAI_API_KEY=local-placeholder
   SELECTED_MODEL=gpt-5.3-codex
   CODEX_OAUTH_TESTING_ENABLED=true
   CODEX_OAUTH_MODE=openai_compatible_bridge
   CODEX_REQUIRE_LOCALHOST=true
   CODEX_ALLOW_PUBLIC_API=false
   ```
2. Start the bridge on the host **before** running the backend:
   ```powershell
   research-agent codex-oauth bridge --host 127.0.0.1 --port 8787
   ```
   *(If the backend runs directly on Windows instead of Docker, use `OPENAI_BASE_URL=http://127.0.0.1:8787/v1`)*

### Enabling CLI Mode:
1. Login via Codex CLI: `codex login`
2. Update `.env`:
   ```ini
   CODEX_OAUTH_TESTING_ENABLED=true
   CODEX_OAUTH_MODE=codex_cli
   ```
3. Test the connection:
   ```powershell
   research-agent codex-oauth status
   research-agent codex-oauth diagnose
   research-agent codex-oauth test "Say hello from Codex OAuth in one sentence."
   ```

### Disabling Codex OAuth:
```ini
CODEX_OAUTH_TESTING_ENABLED=false
CODEX_OAUTH_MODE=disabled
```

---

## Troubleshooting

### "No API key configured"
Ensure your `.env` file contains your chosen provider's key:
```powershell
cat .env
```

### "Module not found"
Ensure you are using your virtual environment and the project is installed in editable mode:
```bash
pip install -e ".[dev]"
```

### Backend won't start in Docker
- Port 8000 might already be in use. Update `API_PORT` in `.env`.
- Missing API keys in `.env`.
- Database error: The SQLite database is stored in `./data/research_agent.db`. To reset:
  ```powershell
  rm data/research_agent.db
  docker compose restart backend
  ```

---

## Quick Reference Commands

| Action | Command |
|--------|---------|
| Initialize DB | `research-agent init` |
| Test LLM | `research-agent test-llm` |
| Discover | `research-agent discover` |
| Start API (dev) | `uvicorn src.api.main:app --reload` |
| Start Docker | `docker compose up -d` |
| View logs | `docker compose logs -f backend` |
| Run tests | `pytest tests/ -v` |
| Lint code | `ruff check src/ --fix` |
