---
trigger: always_on
---

# Project Rules: Overview & Tech Stack

**Project:** Research Agent  
**Created:** January 16, 2026  

---

## Technology Stack

### Core Technologies

| Category | Technology | Version | Notes |
|----------|------------|---------|-------|
| **Language** | Python | 3.11+ | Use type hints everywhere |
| **Agent Framework** | CrewAI | 0.95.0+ | Multi-agent orchestration |
| **LLM Router** | LiteLLM | Latest | Unified LLM interface |
| **Primary LLM** | OpenRouter (free tier) | Latest | Llama 4, DeepSeek, Gemma free models |
| **Fallback LLM** | Ollama (local) | Optional | Only if offline/rate limited |
| **Database** | SQLite | 3.x | Via SQLAlchemy 2.0 |
| **Backend API** | FastAPI | 0.115+ | Async Python |
| **Frontend** | Next.js | 15.x | React 19 |
| **UI Components** | shadcn/ui | Latest | Tailwind-based |
| **CLI** | Click + Rich | Latest | Beautiful terminal |

### Python Dependencies (Core)

```toml
[project]
name = "research-agent"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # Agent Framework
    "crewai>=0.95.0",
    "crewai-tools>=0.14.0",
    "litellm>=1.50.0",
    
    # News & Web
    "feedparser>=6.0.0",
    "ddgs>=6.0.0",
    "trafilatura>=1.12.0",
    "newspaper4k>=0.9.0",
    
    # Keyword Analysis
    "yake>=0.4.8",
    "keybert>=0.8.0",
    
    # YouTube
    "yt-dlp>=2024.0.0",
    
    # Database
    "sqlalchemy>=2.0.0",
    "alembic>=1.14.0",
    
    # API
    "fastapi>=0.115.0",
    "uvicorn>=0.32.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.6.0",
    
    # CLI
    "click>=8.1.0",
    "rich>=13.9.0",
    
    # Utilities
    "python-dotenv>=1.0.0",
    "httpx>=0.28.0",
    "pyyaml>=6.0.0",
]
```

### Development Dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "pre-commit>=4.0.0",
]
```

---

## Project Structure

```
research-agent/
├── src/
│   ├── agents/         # CrewAI agent definitions
│   ├── crews/          # CrewAI crew orchestration
│   ├── tools/          # Custom CrewAI tools
│   ├── database/       # SQLAlchemy models & utils
│   ├── api/            # FastAPI backend
│   ├── cli/            # Click CLI
│   ├── templates/      # Report templates
│   └── core/           # Shared utilities (config, exceptions)
├── web/                # Next.js frontend
├── config/             # Configuration files (channel_profile.yaml, etc.)
├── data/               # Local datasets & SQLite DB
├── tests/              # Test suite
├── .env.example        # Environment template
├── pyproject.toml      # Python project config
└── README.md
```

---

## Related Rule Files

- [rules_python.md](rules_python.md) - Python coding conventions
- [rules_crewai.md](rules_crewai.md) - CrewAI patterns
- [rules_backend.md](rules_backend.md) - Database, API, CLI
- [rules_frontend.md](rules_frontend.md) - Next.js conventions
- [rules_quality.md](rules_quality.md) - Error handling, security, git
