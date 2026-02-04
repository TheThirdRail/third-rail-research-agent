# Project Dependency & Structure Graph

**Date:** January 31, 2026

## Directory Structure
```
research-agent/
├── src/
│   ├── core/               # Core Infrastructure
│   │   ├── config.py       # Settings & Env Vars
│   │   ├── llm_provider.py # LiteLLM Router
│   │   └── model_registry.py # Dynamic Model Fetching
│   ├── agents/             # CrewAI Agents
│   │   ├── config.py       # Role Definitions
│   │   ├── news_aggregator.py
│   │   ├── source_aggregator.py
│   │   ├── bias_classifier.py
│   │   ├── fact_extractor.py
│   │   ├── report_writer.py
│   │   ├── profile_reader.py
│   │   └── relevance_scorer.py
│   ├── tools/              # CrewAI Tools
│   │   ├── rss_aggregator.py
│   │   ├── web_search.py
│   │   ├── article_extractor.py
│   │   ├── bias_classifier.py
│   │   ├── channel_profile_loader.py
│   │   └── youtube_research.py
│   ├── api/                # FastAPI Backend
│   │   ├── main.py         # App Entrypoint
│   │   └── routes/         # API Endpoints
│   │       ├── channel.py
│   │       └── models.py
│   └── cli/                # CLI Entrypoint
│       └── main.py
├── config/                 # Configuration Files
│   ├── channel_profile.yaml
│   └── bias_sources.yaml
├── data/                   # Data Storage
│   └── research_agent.db
├── Dockerfile              # Container Def
├── docker-compose.yml      # Service Orchestration
├── pyproject.toml          # Dependencies
└── README.md               # Documentation
```

## Key Dependencies
- **Implementation:**
  - `src/agents/*.py` -> depends on -> `src/core/llm_provider.py` (via `get_llm_config`)
  - `src/api/routes/models.py` -> depends on -> `src/core/model_registry.py`
  - `src/cli/main.py` -> depends on -> `src/api/routes` logic (shared logic desirable)
  
- **Infrastructure:**
  - `src/core/llm_provider.py` uses `litellm`
  - `src/core/config.py` uses `pydantic-settings`
  - `src/api/main.py` uses `fastapi`
