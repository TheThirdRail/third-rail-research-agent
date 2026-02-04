# Project Context: Research Agent

**Date:** January 31, 2026
**Version:** 2.0.0 (Overhaul)

## Purpose
Research Agent is an AI-powered news research tool for YouTube creators, specifically designed for libertarian/independent media workflows. It aggregates stories, analyzes bias (9-point scale), separates facts from opinions, and generates content outlines.

## Technology Stack
- **Language:** Python 3.11+
- **Agent Framework:** CrewAI 0.95.0+
- **LLM Abstraction:** LiteLLM (Unified interface)
- **Providers:** OpenRouter, Gemini, Anthropic, Groq, OpenAI, Grok, Cerebras, SambaNova, Mistral, Ollama
- **Database:** SQLite + SQLAlchemy 2.0
- **API:** FastAPI 0.115+
- **Frontend:** Next.js 15 (Planned)
- **Containerization:** Docker + docker-compose

## Key Architectural Decisions
1. **Multi-Provider LLM Support:**
   - Implemented `LLMRouter` (src/core/llm_provider.py) using LiteLLM.
   - Removed hardcoded models; introduced `ModelRegistry` (src/core/model_registry.py) for dynamic model fetching.
   - Config supports `selected_model` persistence.
   - **Why:** To avoid vendor lock-in and leverage free tier models (Mistral, Groq, Cerebras).

2. **Channel Scope Profile:**
   - Implemented `ChannelProfileLoader` (src/tools/channel_profile_loader.py).
   - Supports YAML, JSON, Markdown, and text formats.
   - **Why:** allows creators to define their "lens" (worldview, topics) without hardcoding prompts.

3. **Bias Classification Strategy:**
   - Hybrid approach: Local database (`config/bias_sources.yaml`) -> LLM analysis -> Heuristic fallback.
   - **Why:** High accuracy for known sources (fast), adaptable for unknown sources (LLM).

4. **Containerization:**
   - Multi-stage Docker build for Python backend.
   - Compose file includes backend, frontend (placeholder), and Ollama.
   - **Why:** Simplifies deployment and ensures consistent environment.

## Key Files & Roles
- `src/core/llm_provider.py`: Central point for all LLM calls.
- `src/core/model_registry.py`: Fetches/caches models from APIs.
- `src/agents/*.py`: CrewAI agent definitions (News, Bias, Fact, Report, Review, etc.).
- `src/api/routes/*.py`: FastAPI routes for UI interaction.
- `src/cli/main.py`: Command-line interface for headless usage.

## Current State
- **Phase 1-4 Complete:** Project setup, LLM architecture, Channel upload, Core tools/agents.
- **Phase 5 Pending:** Web UI (Next.js) implementation.
- **Phase 6 Pending:** Comprehensive testing suite.
