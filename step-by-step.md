# Step-by-Step: Running Research Agent

This guide covers all the ways to run the Research Agent locally and in Docker.

---

## Prerequisites

| Requirement | Version | Check Command |
|-------------|---------|---------------|
| Python | 3.11+ | `python --version` |
| pip | Latest | `pip --version` |
| Docker (optional) | 20+ | `docker --version` |
| Docker Compose (optional) | v2+ | `docker compose version` |
| Git | Any | `git --version` |

---

## Option 1: Local Development (Recommended for Development)

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

### Step 4: Configure Environment

```bash
# Copy the example environment file
cp .env.example .env
```

Edit `.env` and add your API key(s). You only need ONE provider:

```env
# Choose your provider
LLM_PROVIDER=openrouter

# Add your API key for the chosen provider
OPENROUTER_API_KEY=mock-or-xxxxx
```

**Free-tier providers:** OpenRouter ✅, Gemini ✅, Groq ✅, Cerebras ✅, Mistral ✅, Ollama ✅ (local)

### Step 5: Initialize and Test

```bash
# Initialize database
research-agent init

# Test LLM connection
research-agent test-llm
```

### Step 6: Run the API Server

```bash
# Start FastAPI server
uvicorn src.api.main:app --reload --port 8000
```

Access: <http://localhost:8000/docs>

### Step 7: Use the CLI

```bash
# Discover stories for your channel
research-agent discover

# Analyze a specific story
research-agent analyze --describe "Your story description"
```

---

## Option 2: Docker Deployment (Recommended for Production)

### Step 1: Clone and Configure

```bash
git clone https://github.com/TheThirdRail/third-rail-research-agent.git
cd third-rail-research-agent

# Copy environment template
cp .env.example .env
```

Edit `.env` and add your API keys.

### Step 2: Build and Start All Services

```bash
docker compose up --build -d
```

This starts:

- **Backend API**: <http://localhost:8000>
- **Frontend UI**: <http://localhost:3000> (if web/ exists)

### Step 3: Verify Services

```bash
# Check health
curl http://localhost:8000/health

# View logs
docker compose logs -f backend
```

### Step 4: Using with Local Ollama

To use local Ollama for free LLM inference:

```bash
# Start with Ollama profile
docker compose --profile local-llm up --build -d

# Pull a model
docker exec research-agent-ollama ollama pull llama3.1:8b
```

Update `.env`:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
```

### Step 5: Stop Services

```bash
docker compose down
```

---

## Option 3: API-Only Mode

Run just the backend API without Docker:

```bash
# Terminal 1: Start API
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Make requests
curl http://localhost:8000/api/config
curl http://localhost:8000/api/models
```

---

## Optional Codex OAuth Testing

Codex OAuth testing is optional and local-only. It is intended to let this app talk to a locally authenticated Codex/OAuth workflow while developing. Do not paste ChatGPT cookies, browser session tokens, copied bearer tokens, or refresh tokens into this project. Do not expose Codex-backed access publicly.

Bridge mode uses a separate local OpenAI-compatible Codex/OAuth bridge:

```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=http://host.docker.internal:8787/v1
OPENAI_API_KEY=local-placeholder
SELECTED_MODEL=gpt-5.3-codex
CODEX_OAUTH_TESTING_ENABLED=true
CODEX_OAUTH_MODE=openai_compatible_bridge
CODEX_REQUIRE_LOCALHOST=true
CODEX_ALLOW_PUBLIC_API=false
```

Start the bridge on the host before running the Docker backend:

```powershell
research-agent codex-oauth bridge --host 127.0.0.1 --port 8787
```

The bridge provides `GET /health`, `GET /v1/models`, `POST /v1/chat/completions`, and `POST /v1/responses`.

If the backend runs directly on Windows instead of Docker, use `OPENAI_BASE_URL=http://127.0.0.1:8787/v1`.

CLI mode uses the official Codex CLI after you log in outside this app:

```powershell
codex login
research-agent codex-oauth status
research-agent codex-oauth diagnose
research-agent codex-oauth test "Say hello from Codex OAuth in one sentence."
```

Turn it off with:

```env
CODEX_OAUTH_TESTING_ENABLED=false
CODEX_OAUTH_MODE=disabled
```

# Codex OAuth Testing Notes

## Implemented mode

Bridge mode and CLI mode.

## How to enable

For bridge mode, run `research-agent codex-oauth bridge --host 127.0.0.1 --port 8787`, then set `LLM_PROVIDER=openai`, `OPENAI_BASE_URL=http://host.docker.internal:8787/v1`, `OPENAI_API_KEY=local-placeholder`, `SELECTED_MODEL=gpt-5.3-codex`, `CODEX_OAUTH_TESTING_ENABLED=true`, and `CODEX_OAUTH_MODE=openai_compatible_bridge`.

For CLI mode, run `codex login`, then set `CODEX_OAUTH_TESTING_ENABLED=true` and `CODEX_OAUTH_MODE=codex_cli`.

## How to test

```powershell
research-agent codex-oauth status
research-agent codex-oauth diagnose
research-agent codex-oauth test "Say hello from Codex OAuth in one sentence."
research-agent test-llm --provider openai
```

## How to disable

```env
CODEX_OAUTH_TESTING_ENABLED=false
CODEX_OAUTH_MODE=disabled
```

## Limitations

Bridge mode depends on the official `codex exec` command being installed and logged in on the host running `research-agent codex-oauth bridge`.

## Safety guardrails

Bridge URLs are local-only by default, `0.0.0.0` is blocked, prompt length is capped, subprocess calls use `shell=False`, diagnostics redact secret-looking strings, and the app never reads Codex token files or asks for browser/session tokens.

---

## Configuration Reference

| Environment Variable | Description | Required |
|---------------------|-------------|----------|
| `LLM_PROVIDER` | Primary provider (openrouter, gemini, etc.) | Yes |
| `OPENROUTER_API_KEY` | OpenRouter API key | If using OpenRouter |
| `GOOGLE_API_KEY` | Google Gemini API key | If using Gemini |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | If using Anthropic |
| `GROQ_API_KEY` | Groq API key | If using Groq |
| `OPENAI_API_KEY` | OpenAI API key | If using OpenAI |
| `XAI_API_KEY` | xAI Grok API key | If using Grok |
| `CEREBRAS_API_KEY` | Cerebras API key | If using Cerebras |
| `SAMBANOVA_API_KEY` | SambaNova API key | If using SambaNova |
| `MISTRAL_API_KEY` | Mistral API key | If using Mistral |
| `SELECTED_MODEL` | Override default model | Optional |
| `ANALYSIS_MODEL` | Model for analysis tasks | Optional |
| `DATABASE_URL` | SQLite path | Default provided |

---

## Troubleshooting

### "No API key configured"

Ensure your `.env` file has the correct key:

```bash
cat .env | grep API_KEY
```

### "Module not found"

Reinstall in editable mode:

```bash
pip install -e ".[dev]"
```

### Docker build fails

Check Docker is running:

```bash
docker info
```

### Port already in use

Change the port:

```bash
uvicorn src.api.main:app --port 8001
```

---

## Quick Command Reference

| Action | Command |
|--------|---------|
| Start API (dev) | `uvicorn src.api.main:app --reload` |
| Start Docker | `docker compose up -d` |
| Stop Docker | `docker compose down` |
| View logs | `docker compose logs -f backend` |
| Run tests | `pytest tests/ -v` |
| Lint code | `ruff check src/` |
| Format code | `ruff format src/` |
