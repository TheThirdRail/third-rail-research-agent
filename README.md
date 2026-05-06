# Research Agent

AI-powered news research and political bias analysis for YouTube creators. 
Built to provide multi-source aggregation, a 9-point bias classification, semantic query expansion, and clear separation of facts, visual evidence, and editorial content.

## Features

- **Multi-Source Aggregation**: Pulls and extracts coverage across the political spectrum using curated RSS feeds and DuckDuckGo search.
- **Hardened Semantic Memory**: Uses **LanceDB** as a high-performance vector store for indexing source-grounded chunks, enabling agents to retrieve original facts and evidence.
- **9-Point Bias Classification**: Rates sources from Far Left (-4) to Far Right (+4) using local datasets and LLM fallback, enforcing ideological balance in research.
- **Fact vs. Opinion & Visual Evidence**: Distinguishes verifiable facts and directly observable visual evidence from editorial interpretation.
- **Structured Observability**: Built-in **Diagnostics** and **Handoff** tracking for auditing agent reasoning and retrieval precision.
- **Benchmark Harness**: Automated scenario-based testing (e.g., ideological coverage, actor overlap) to ensure pipeline stability.
- **Multi-LLM Support**: Supports OpenRouter, Gemini, Anthropic, Groq, Mistral, Cerebras, SambaNova, OpenAI, and local Ollama.
- **Docker & Local Deployment**: One-command deployment with Docker Compose.

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
Edit `.env` and configure at least one LLM provider. **OpenRouter** is recommended.
```ini
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here

# Semantic features (Hardened P2 Configuration)
SEMANTIC_MEMORY_ENABLED=true
SEMANTIC_QUERY_EXPANSION_ENABLED=true
SEMANTIC_VECTOR_STORE=lancedb
```

### 3. Initialize & Run
```bash
# Initialize SQLite database, LanceDB, and run Alembic migrations
research-agent init

# Verify system readiness (API, migrations, OCR, Vector Store)
research-agent health --strict

# Start FastAPI server
uvicorn src.api.main:app --reload
```

> **For more detailed setup instructions**, please see the [Step-by-Step Guide](step-by-step.md).

### Windows PowerShell Note

If CLI output fails with Unicode or encoding errors, set:

```powershell
$env:PYTHONIOENCODING="utf-8"
```

To persist for the project, add to your local `.env`:

```ini
PYTHONIOENCODING=utf-8
```

## Usage

### CLI Commands

**Discovery & Analysis**
```bash
research-agent discover --topics "geopolitics, economy"
research-agent analyze --describe "New tax bill passed"
```

**Observability & Debugging**
```bash
# Show detailed diagnostics for an analysis run
research-agent diagnostics <story_id>

# Inspect agent handoffs at specific stages
research-agent handoff <story_id> --stage post-retrieval
```

**Quality Control**
```bash
# Run scenario benchmarks
research-agent benchmark --live --live-limit 1

# Validate OCR pipeline
research-agent validate-ocr --force
```

## Architecture & Project Structure

Research Agent uses **CrewAI** for orchestration, **FastAPI** for the backend, and **LanceDB** for semantic memory.

```
research-agent/
├── src/
│   ├── agents/        # CrewAI agents
│   ├── crews/         # Agent orchestrations
│   ├── tools/         # RSS, Search, Bias, Extractor
│   ├── database/      # SQLAlchemy models & migrations
│   ├── services/      # Analysis, SemanticMemory, VisualEvidence
│   ├── core/          # Configuration & LLM Routing
│   └── api/           # FastAPI backend
├── benchmarks/        # Scenario-based test fixtures
├── config/            # YAML configs (bias_sources, rss_feeds)
├── docs/              # Technical documentation
├── tests/             # Pytest suite
└── web/               # Next.js frontend
```

## Current Status
- **Hardening P2**: Mostly implemented on `dev`; remaining work is focused on retrieval-family wiring, test-suite verification, migration policy, and diagnostic polish.
- **Backend API**: Functional, with continued hardening.
- **Web Interface**: In progress.
- **Production readiness**: Not final yet. Run the pytest suite and benchmark harness before production use.

## License
MIT License.
