# Research Agent

AI-powered news research and political bias analysis for YouTube creators. 
Built to provide multi-source aggregation, a 9-point bias classification, semantic query expansion, and clear separation of facts, visual evidence, and editorial content.

## Features

- **Multi-Source Aggregation**: Pulls and extracts coverage across the political spectrum using curated RSS feeds and DuckDuckGo search with current-story **Semantic Query Expansion**.
- **Semantic Memory**: Indexes source-grounded chunks in SQL by default so agent reasoning can retrieve original facts rather than only summaries. Optional external vector backends are configured separately.
- **9-Point Bias Classification**: Rates sources from Far Left (-4) to Far Right (+4) using local datasets and LLM fallback, enforcing ideological balance in research.
- **Fact vs. Opinion & Visual Evidence**: Distinguishes verifiable facts and directly observable visual evidence from editorial interpretation and legal characterization.
- **Multi-LLM Support**: Supports OpenRouter, Gemini, Anthropic, Groq, Mistral, Cerebras, SambaNova, OpenAI, and local Ollama (via LiteLLM).
- **Channel Scope Profiling**: Upload your channel profile (worldview, topics) to personalize story discovery and receive tailored outlines.
- **Docker & Local Deployment**: One-command deployment with Docker Compose, or run locally via `uvicorn`.

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

### 2. Configure Environment
```bash
cp .env.example .env
```
Edit `.env` and configure at least one LLM provider. **OpenRouter** is recommended as a unified interface.
```ini
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here

# Optional semantic features
SEMANTIC_MEMORY_ENABLED=true
SEMANTIC_QUERY_EXPANSION_ENABLED=true
SEMANTIC_VECTOR_STORE=none
```

### 3. Initialize & Run
```bash
# Initialize SQLite database and run Alembic migrations
research-agent init

# Verify provider, schema, migration, screenshot, and OCR readiness
research-agent health --strict

# Test your LLM connection
research-agent test-llm

# Start FastAPI server
uvicorn src.api.main:app --reload
```

> **For more detailed setup instructions, including Docker and API keys**, please see the [Step-by-Step Guide](step-by-step.md).

## Usage

### CLI Commands

**Discover Stories**
```bash
research-agent discover
research-agent discover --topics "geopolitics, economy"
```

**Analyze a Specific Story**
```bash
research-agent analyze --describe "New tax bill passed"
research-agent analyze --url "https://example.com/news/article"
```

**Operational Checks**
```bash
research-agent health --strict
research-agent validate-ocr --force
research-agent benchmark --live --live-limit 1 --format markdown
```

**Manage Your Channel Profile**
```bash
research-agent profile upload -f my-channel.yaml
research-agent profile show
```

## Architecture & Project Structure

Research Agent uses **CrewAI** for multi-agent orchestration, **FastAPI** for its backend API, and **SQLAlchemy/Alembic** for SQLite data persistence. SQL-backed semantic memory is the default local retrieval path; LanceDB remains optional and out of the default setup.

```
research-agent/
├── src/
│   ├── agents/        # CrewAI agents (Profile Reader, Fact Extractor, etc.)
│   ├── crews/         # Agent orchestrations (Discovery Crew, Analysis Crew)
│   ├── tools/         # RSS, DuckDuckGo search, Bias Classification, Extractor
│   ├── database/      # SQLAlchemy models & migrations
│   ├── api/           # FastAPI backend & routes
│   ├── cli/           # Click-based command line interface
│   ├── core/          # Configuration, LLMRouter, EmbeddingProvider 
│   └── services/      # Business logic (SemanticMemoryService, StoryParserService)
├── config/            # YAML configs (bias_sources, rss_feeds)
├── data/              # SQLite DB and local artifacts
├── docs/              # Implementation guides (Semantic Search, etc.)
├── tests/             # Pytest test suite
├── web/               # Next.js frontend (in development)
├── Dockerfile         # Multi-stage build definition
├── docker-compose.yml # Compose config for Backend, Frontend, and Ollama
├── step-by-step.md    # Detailed run instructions
└── pyproject.toml     # Project metadata and tool configuration
```

## Advanced Analytics Flow
Our evidence gathering is treated as four separate layers:
1. **Observable Facts** (what is directly seen in an image/video/post)
2. **Direct News Reporting** (what happened)
3. **Ideological Framing** (how left/center/right buckets interpret it)
4. **Creator-Facing Synthesis** (video outlines)

## Current Status
- **Phase 1-5**: Core Foundation, LLM Integration, CLI Tools, and Agents are **Complete**.
- **Phase 6**: CLI Interface is **Complete**.
- **Phase 7**: FastAPI Backend & Semantic Memory architecture are **In Progress**.
- **Phase 8**: Next.js Web Interface is **Pending**.

## Local Quality Control & Testing
We use strict typing and formatting standards:
```bash
ruff format src/
ruff check src/ --fix
mypy src/
pytest tests/ -v
```

## License
MIT License.
