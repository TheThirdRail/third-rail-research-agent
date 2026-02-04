# Research Agent

AI-powered news research for YouTube creators with multi-source political bias analysis.

## Features

- **Multi-Source Aggregation** — Find coverage across the political spectrum
- **9-Point Bias Classification** — Rate sources from Far Left to Far Right
- **Fact vs Opinion Separation** — Distinguish verifiable facts from editorial content
- **Multi-LLM Support** — Use OpenRouter, Gemini, Anthropic, Groq, and more
- **Budget Enforcement** — Set spending limits; $0 = free models only
- **Channel Scope Upload** — Personalize story discovery with your channel profile
- **Docker Ready** — One-command deployment with docker-compose

## Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/TheThirdRail/third-rail-research-agent.git
cd third-rail-research-agent

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and set ONE LLM provider:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here
```

**Free-tier providers:** OpenRouter ✅, Gemini ✅, Groq ✅, Cerebras ✅, Mistral ✅, Ollama ✅

### 3. Run

```bash
# Initialize database
research-agent init

# Test LLM connection
research-agent test-llm

# Start API server
uvicorn src.api.main:app --reload
```

**Detailed instructions:** See [step-by-step.md](step-by-step.md)

## Usage

### Discover Stories

```bash
research-agent discover
research-agent discover --topics "ukraine,bitcoin"
```

### Analyze a Story

```bash
research-agent analyze --describe "DOGE cuts government spending"
research-agent analyze --url "https://example.com/article"
```

### Manage Channel Profile

```bash
research-agent profile upload -f my-channel.md
research-agent profile show
```

## Docker Deployment

```bash
# Standard deployment
docker compose up --build -d

# With local Ollama
docker compose --profile local-llm up --build -d
```

**Services:**

| Service | URL | Description |
|---------|-----|-------------|
| Backend API | <http://localhost:8000> | FastAPI + CrewAI |
| Frontend UI | <http://localhost:3000> | Next.js (coming soon) |
| Ollama | <http://localhost:11434> | Local LLM (optional) |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health check |
| `/api/config` | GET | Current LLM configuration |
| `/api/channel/profile` | GET | Get channel profile |
| `/api/channel/upload` | POST | Upload channel scope |
| `/api/models` | GET | List available models |
| `/api/models/select` | POST | Set active model |
| `/api/budget` | GET | Get budget status |
| `/api/budget/limit` | POST | Set budget limit |
| `/api/discover` | POST | Discover relevant stories |
| `/api/analyze` | POST | Analyze a story |

## Project Structure

```
research-agent/
├── src/
│   ├── agents/        # CrewAI agent definitions
│   ├── crews/         # Agent crew orchestrations
│   ├── tools/         # Custom tools (RSS, search, bias)
│   ├── database/      # SQLAlchemy models
│   ├── api/           # FastAPI backend
│   ├── cli/           # Click CLI
│   ├── core/          # Config & LLM provider
│   └── services/      # Business logic
├── web/               # Next.js frontend (coming soon)
├── config/            # YAML configs
├── tests/             # Test suite
├── Dockerfile
├── docker-compose.yml
├── step-by-step.md    # Detailed run instructions
└── pyproject.toml
```

## Configuration

### Channel Profile

Create `config/channel_profile.yaml`:

```yaml
channel:
  name: "Your Channel Name"
  worldview: libertarian
  description: "Your channel description"

topics:
  primary:
    - politics
    - news
    - geopolitics
```

### Budget Control

Set budget via API or environment:

- `$0.00` = Free models only
- `$5.00` = Allow up to $5/day in LLM costs

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Format code
ruff format src/
ruff check src/ --fix

# Type check
mypy src/
```

## Current Limitations

- **No per-agent LLM configuration** — All agents share the same provider/model
- **Model selection not persisted** — Selection is session-only (fix planned)

## License

MIT License — see LICENSE file.
