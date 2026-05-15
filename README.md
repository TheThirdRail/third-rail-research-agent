# Research Agent

An AI-powered system for automating news research, multi-source bias analysis, and content preparation. Built for independent content creators who need structured, fact-based research with clear perspective labeling across the political spectrum.

## Features

- **Multi-Source Aggregation** — Pulls coverage across the political spectrum using RSS feeds and DuckDuckGo search
- **9-Point Political Bias Classification** — Rates sources from Far Left (-4) to Far Right (+4) using dataset-driven classification and LLM validation
- **Semantic Memory & Retrieval** — SQL-backed semantic memory by default, with an optional LanceDB vector index for local advanced retrieval
- **Fact vs. Opinion Separation** — Clearly distinguishes verifiable facts and visual evidence from editorial interpretation
- **Balanced Source Planning** — Enforces ideological distribution across story coverage (left-side, center, right-side)
- **Observability & Diagnostics** — Built-in handoff tracking and diagnostic commands for auditing agent reasoning and retrieval
- **Benchmark Harness** — Automated scenario testing to validate pipeline stability across edge cases
- **Multi-LLM Support** — Compatible with OpenRouter, Anthropic Claude, Google Gemini, Groq, Cerebras, SambaNova, Mistral, xAI, local Ollama, and LM Studio
- **CLI + Web UI** — Terminal interface for power users; Next.js web interface for visual workflow

## Quick Start

### Prerequisites

- Python 3.11+ (3.12 tested)
- Docker and Docker Compose (optional, for containerized deployment)
- At least one configured LLM provider API key (see [Deployment Guide](deployment-guide.md))

### Local Development (5 minutes)

```bash
# Clone and enter project
git clone https://github.com/TheThirdRail/third-rail-research-agent.git
cd third-rail-research-agent

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env and add at least one LLM provider API key (OpenRouter recommended)

# Initialize database and verify system
research-agent init
research-agent health --strict

# Start FastAPI backend (separate terminal)
uvicorn src.api.main:app --reload

# Install and start Next.js frontend (separate terminal)
npm --prefix web ci
npm --prefix web run dev
```

### Docker Deployment (3 commands)

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your LLM provider keys

# Build and start services
docker compose up --build

# Services available at:
# - Backend: http://localhost:8000
# - Frontend: http://localhost:3000
# - API docs: http://localhost:8000/docs
```

See [Deployment Guide](deployment-guide.md) for detailed setup, [Docker Setup Guide](docs/docker-setup-guide.md) for container troubleshooting, and [Docker Restart Instructions](docs/docker-restart-instructions.md) when you want to rebuild and try the app locally.

## Usage

### Discovery Mode — Find Stories

```bash
# Discover 10 stories across your channel topics
research-agent discover --topics "geopolitics, economy"

# Get detailed diagnostics for why stories were selected
research-agent diagnostics <story_id>
```

### Analysis Mode — Research a Story

```bash
# Analyze a specific story by URL or description
research-agent analyze --url "https://example.com/story"
research-agent analyze --describe "New tax bill passed by Congress"

# Output: JSON report + Markdown outline for video content
```

### Quality Control

```bash
# Run scenario-based benchmarks (tests edge cases and bias balance)
research-agent benchmark --live --live-limit 1

# Validate OCR pipeline for visual evidence extraction
research-agent validate-ocr --force

# Inspect agent handoffs at specific analysis stages
research-agent handoff <story_id> --stage post-retrieval
```

### Web Interface

1. Navigate to **http://localhost:3000** (or your configured frontend URL)
2. Input a story URL or description
3. View sources, bias ratings, fact matrix, and generated outline
4. Download report as Markdown or JSON

## Architecture

Research Agent uses **CrewAI** for agent orchestration, **FastAPI** for the backend, **Next.js** for the frontend, SQL for the default semantic memory path, and optional LanceDB for vector indexing.

### Core Workflows

**Discovery Crew** — Finds relevant stories:
- Profile Reader Agent (extracts channel topics)
- News Aggregator Agent (RSS + DuckDuckGo search)
- Relevance Scorer Agent (ranks by topic match and trending signals)
- Performance Predictor Agent (boosts stories with strong historical audience response)

**Analysis Crew** — Researches a specific story:
- Story Parser Agent (extracts story details from URL/description)
- Source Aggregator Agent (finds all sources covering the story)
- Bias Classifier Agent (rates each source on 9-point scale)
- Fact Extractor Agent (separates facts from opinions)
- Narrative Analyzer Agent (identifies mainstream vs. alternative narratives)
- Report Writer Agent (generates comprehensive report + video outline)

### Project Structure

```
research-agent/
├── src/
│   ├── agents/              # CrewAI agent definitions
│   ├── crews/               # Agent orchestrations (Discovery, Analysis)
│   ├── tools/               # RSS, search, bias classification, extraction
│   ├── database/            # SQLAlchemy models and Alembic migrations
│   ├── services/            # Analysis, semantic memory, visual evidence
│   ├── core/                # Configuration, LLM routing, settings
│   ├── api/                 # FastAPI backend endpoints
│   └── cli/                 # Click CLI commands
├── web/                     # Next.js frontend
├── tests/                   # Pytest test suite
├── config/                  # YAML: bias sources, RSS feeds, scenario fixtures
├── benchmarks/              # Scenario-based test cases
├── docs/                    # Technical documentation
└── docker-compose.yml       # Three-service deployment (backend, frontend, ollama)
```

## Configuration

All configuration is environment-driven via `.env` file. Key settings:

| Setting | Purpose | Example |
|---------|---------|---------|
| `LLM_PROVIDER` | Default LLM provider | `openrouter` |
| `OPENROUTER_API_KEY` | OpenRouter API key (recommended) | Your key here |
| `SEMANTIC_MEMORY_ENABLED` | Enable SQL-backed semantic memory indexing | `true` or `false` |
| `SEMANTIC_VECTOR_STORE` | Optional vector index backend | `none` or `lancedb` |
| `SEMANTIC_QUERY_EXPANSION_ENABLED` | Expand queries with LLM | `true` or `false` |
| `CANDIDATE_PROBE_LIMIT` | Max initial sources to probe | `15` |
| `RETAINED_SOURCE_MIN/MAX` | Final source count range | `3` / `5` |
| `STRICT_BUCKET_ENFORCEMENT` | Enforce left/center/right balance | `true` |

See `.env.example` for all options and detailed explanations.

## LLM Provider Setup

### OpenRouter (Recommended)

1. Create account at [openrouter.ai](https://openrouter.ai/keys)
2. Generate API key
3. Add to `.env`:
   ```
   LLM_PROVIDER=openrouter
   OPENROUTER_API_KEY=replace-with-openrouter-api-key
   ```
4. Select model in UI or via `SELECTED_MODEL` env var

### Local/Offline (Ollama)

1. Install [Ollama](https://ollama.ai)
2. Pull a model: `ollama pull llama2`
3. Configure `.env`:
   ```
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   ```

### Other Providers

Supports: OpenAI, Anthropic Claude, Google Gemini, Groq, Cerebras, SambaNova, Mistral, xAI (Grok), and LM Studio.

See [Deployment Guide](deployment-guide.md) for complete provider configuration.

## Current Status

- **Backend and CLI:** Active development, with database initialization managed through `research-agent init`.
- **Web UI:** Available through the Next.js frontend at `http://localhost:3000`.
- **Semantic memory:** SQL-backed by default; LanceDB remains opt-in through `SEMANTIC_VECTOR_STORE=lancedb`.

**Production Readiness:** Not final. Run the full pytest suite, frontend checks, and benchmark harness before production use. See [Docker Setup Guide](docs/docker-setup-guide.md) for container health checks.

## Commands Reference

### CLI Entry Point
```bash
research-agent --help              # Full command list
research-agent discover            # Story discovery
research-agent analyze             # Analyze a story
research-agent diagnostics <id>    # Debug analysis run
research-agent handoff <id>        # View agent handoffs
research-agent benchmark           # Run scenario tests
research-agent validate-ocr        # Test visual evidence pipeline
research-agent init                # Initialize database
research-agent health --strict     # System readiness check
```

### Docker Commands
```bash
docker compose up --build          # Start all services
docker compose down                # Stop services
docker compose logs -f backend     # Stream backend logs
docker compose --profile local-llm up  # Include Ollama service
```

For a clean local restart after code or config changes, follow [Docker Restart Instructions](docs/docker-restart-instructions.md).

## Support & Debugging

- **Setup Issues** → [Docker Setup Guide](docs/docker-setup-guide.md)
- **Docker Restart** → [Docker Restart Instructions](docs/docker-restart-instructions.md)
- **Deployment** → [Deployment Guide](deployment-guide.md)
- **Technical Details** → [Product Requirements](prd.md)
- **Repository** → [GitHub](https://github.com/TheThirdRail/third-rail-research-agent)

## License

MIT License. See LICENSE file for details.
