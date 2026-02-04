# Research Agent - Implementation Checklist

**Project Restart:** January 31, 2026  
**Reference:** [prd.md](file:///d:/Coding/Research-Agent/prd.md) | [implementation_plan.md](file:///C:/Users/jerem/.gemini/antigravity/brain/3364b28e-22d3-4895-8904-dee2afdfe60f/implementation_plan.md)

---

## Phase 1: Foundation ✅

### 1.1 Project Setup
- [x] Initialize Python project with pyproject.toml
- [x] Create .gitignore with comprehensive exclusions
- [x] Create .env.example with 9 LLM providers
- [x] Create local rules in .agent/rules/

### 1.2 Docker Configuration
- [x] Create multi-stage Dockerfile
- [x] Create docker-compose.yml (backend, frontend, ollama)
- [x] Create .dockerignore
- [ ] Test `docker compose up --build`

### 1.3 Database Setup
- [x] Create SQLAlchemy models (Story, Source, Analysis, VideoPerformance)
- [x] Create database initialization function
- [ ] Initialize Alembic migrations

---

## Phase 2: LLM Provider Architecture ✅

### 2.1 Multi-Provider Support
- [x] Create `src/core/llm_provider.py` with LLMRouter
- [x] Support all providers: OpenRouter, Gemini, Anthropic, Groq, OpenAI, Grok, Cerebras, SambaNova, Mistral, Ollama

### 2.2 Dynamic Model Selection
- [x] Create `src/core/model_registry.py` with model fetching
- [x] Create `src/api/routes/models.py` with list/select endpoints
- [x] Remove hardcoded `DEFAULT_MODEL` - use `selected_model`
- [x] Add Mistral as new provider

### 2.3 Configuration
- [x] Update `src/core/config.py` with all provider settings
- [x] Add `MISTRAL_API_KEY` setting
- [x] Update `.env.example` with dynamic model selection

### 2.4 Test LLM Provider
- [x] Add CLI command: `research-agent test-llm`
- [ ] Create unit testscommand

---

## Phase 3: Channel Scope Upload ✅

### 3.1 Document Processing
- [x] Create `src/tools/channel_profile_loader.py`
- [x] Support YAML, JSON, Markdown, plain text
- [x] Parse topics, worldview, preferences

### 3.2 API & CLI
- [x] Create `POST /api/channel/upload` endpoint
- [x] Create `GET /api/channel/profile` endpoint
- [x] Add `research-agent profile upload` CLI
- [x] Add `research-agent profile show` CLI

---

## Phase 4: Core Tools ✅

### 4.1 News Tools
- [x] RSS Aggregator - `src/tools/rss_aggregator.py`
- [x] Web Search (DuckDuckGo) - `src/tools/web_search.py`
- [x] Article Extractor - `src/tools/article_extractor.py`
- [x] Keyword Extractor - `src/tools/keyword_extractor.py`
- [x] YouTube Research - `src/tools/youtube_research.py`

### 4.2 Bias Classification
- [x] Bias Classifier Tool - `src/tools/bias_classifier.py`
- [x] Local bias sources database - `config/bias_sources.yaml`
- [x] LLM fallback for unknown sources
- [ ] Download MBFC dataset

---

## Phase 5: CrewAI Agents ✅

### 5.1 Agent Definitions
- [x] Profile Reader Agent - `src/agents/profile_reader.py`
- [x] News Aggregator Agent - `src/agents/news_aggregator.py`
- [x] Relevance Scorer Agent - `src/agents/relevance_scorer.py`
- [x] Source Aggregator Agent - `src/agents/source_aggregator.py`
- [x] Bias Classifier Agent - `src/agents/bias_classifier.py`
- [x] Fact Extractor Agent - `src/agents/fact_extractor.py`
- [ ] Narrative Analyzer Agent - `src/agents/narrative_analyzer.py`
- [x] Report Writer Agent - `src/agents/report_writer.py`

### 5.2 Crews
- [/] Discovery Crew - `src/crews/discovery_crew.py`
- [/] Analysis Crew - `src/crews/analysis_crew.py`

---

## Phase 6: CLI Interface

### 6.1 Commands
- [x] `research-agent init` - Initialize database
- [x] `research-agent discover` - Find stories
- [x] `research-agent analyze` - Analyze story
- [x] `research-agent report` - Manage reports
- [x] `research-agent performance` - Track metrics
- [x] `research-agent profile upload/show` - Manage profile
- [x] `research-agent test-llm` - Test LLM connection

---

## Phase 7: FastAPI Backend

### 7.1 Core API
- [x] Create `src/api/main.py` with FastAPI app
- [x] Add CORS middleware for frontend
- [x] Health check endpoint

### 7.2 Routes
- [x] Channel routes - `src/api/routes/channel.py`
- [ ] Discovery routes - `src/api/routes/discover.py`
- [ ] Analysis routes - `src/api/routes/analyze.py`
- [ ] Reports routes - `src/api/routes/reports.py`
- [ ] Performance routes - `src/api/routes/performance.py`
- [ ] WebSocket for progress

---

## Phase 8: Next.js Frontend

### 8.1 Setup
- [ ] Initialize Next.js app in `web/`
- [ ] Install shadcn/ui
- [ ] Configure Tailwind theme
- [ ] Create Dockerfile for frontend

### 8.2 Pages
- [ ] Dashboard - `/`
- [ ] Discovery - `/discover`
- [ ] Analysis - `/analyze`
- [ ] Report Viewer - `/report/[id]`
- [ ] History - `/history`
- [ ] Settings - `/settings`

### 8.3 Components
- [ ] BiasIndicator (9-point scale)
- [ ] StoryCard
- [ ] SourceMatrix
- [ ] FactComparison
- [ ] ProgressStream (WebSocket)

---

## Phase 9: Testing

### 9.1 Unit Tests
- [ ] Test LLM provider switching
- [ ] Test channel profile loader
- [ ] Test bias classifier
- [ ] Test API routes

### 9.2 Integration Tests
- [ ] Docker compose startup
- [ ] End-to-end discovery
- [ ] End-to-end analysis

---

## Legend

| Symbol | Meaning |
|--------|---------|
| [ ] | Not started |
| [/] | In progress (stub exists) |
| [x] | Complete |
