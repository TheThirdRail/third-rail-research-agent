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
