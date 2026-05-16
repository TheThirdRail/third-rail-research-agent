# =========================================
# Research Agent Minimal Configuration
# =========================================
# Copy this file to .env and adjust local host/port values as needed.
# This example uses only:
# - Codex OAuth through a local OpenAI-compatible bridge for chat/completions.
# - LM Studio only for semantic embeddings.

# -----------------------------------------
# Application Settings
# -----------------------------------------
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO
# Force UTF-8 stdout/stderr encoding (avoids Windows Unicode errors)
PYTHONIOENCODING=utf-8

# -----------------------------------------
# API Settings (FastAPI Backend)
# -----------------------------------------
API_HOST=0.0.0.0
API_PORT=8000
# Shared secret protecting admin/mutation API routes.
# Leave empty to disable admin routes entirely.
# Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"
ADMIN_API_KEY=
# Server-side secret used by the Next.js frontend to sign admin session cookies.
# Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"
ADMIN_SESSION_SECRET=
# Comma-separated allowed CORS origins. Defaults to localhost:3000 when empty.
CORS_ORIGINS=

# -----------------------------------------
# Web UI Settings (Next.js Frontend)
# -----------------------------------------
NEXT_PUBLIC_API_URL=http://localhost:8000

# -----------------------------------------
# Database
# -----------------------------------------
# SQLite path is relative to project root.
# The data/ folder is created automatically.
DATABASE_URL=sqlite:///data/research_agent.db

# =========================================
# LLM: Codex OAuth Bridge Only
# =========================================
# Start the local bridge before running analysis:
# research-agent codex-oauth bridge --host 127.0.0.1 --port 8787
LLM_PROVIDER=openai
SELECTED_MODEL=
ANALYSIS_MODEL=
OPENAI_BASE_URL=http://host.docker.internal:8787/v1
# Placeholder only. Do not put a real OpenAI API key here for Codex OAuth bridge mode.
OPENAI_API_KEY=local-placeholder

CODEX_OAUTH_TESTING_ENABLED=true
CODEX_OAUTH_MODE=openai_compatible_bridge
CODEX_CLI_COMMAND=codex
CODEX_REQUIRE_LOCALHOST=true
CODEX_ALLOW_PUBLIC_API=false
CODEX_MAX_PROMPT_CHARS=30000
CODEX_TIMEOUT_SECONDS=300

# =========================================
# Embeddings: LM Studio Only
# =========================================
# For Docker backend -> host LM Studio, use host.docker.internal.
# For non-Docker backend -> host LM Studio, change to http://localhost:1234/v1.
LM_STUDIO_API_BASE=http://host.docker.internal:1234/v1
LM_STUDIO_API_KEY=lm-studio

# =========================================
# Web Search (SearxNG)
# =========================================
SEARXNG_BASE_URL=http://host.docker.internal:8080
SEARXNG_API_KEY=

# =========================================
# Article Extraction
# =========================================
CRAWL4AI_HEADLESS=true
CRAWL4AI_PROGRESSIVE_UNDETECTED_ENABLED=true
CRAWL4AI_PAGE_TIMEOUT_MS=60000
CRAWL4AI_DELAY_BEFORE_RETURN_HTML=2.0

# =========================================
# Source Gathering Policy
# =========================================
CANDIDATE_PROBE_LIMIT=15
RETAINED_SOURCE_MIN=2
RETAINED_SOURCE_MAX=10
SEARCH_TIME_WINDOW_DAYS=7
STRICT_BUCKET_ENFORCEMENT=true
REQUIRED_BUCKET_GROUPS=left_side,right_side
EXACT_CENTER_PREFERRED=true
MAX_PER_EXACT_BIAS=1
MAX_PER_BUCKET_GROUP=2
ALLOW_SAME_BIAS_BACKFILL=false
ANALYSIS_RSS_FIRST_ENABLED=true
ANALYSIS_RSS_TIMEOUT_SECONDS=6
ANALYSIS_RSS_MAX_FEEDS_PER_BUCKET=3
RSS_CANDIDATE_MIN_STORY_SCORE=0.40

# =========================================
# Semantic Search / Memory
# =========================================
SEMANTIC_QUERY_EXPANSION_ENABLED=false
SEMANTIC_QUERY_EXPANSION_MAX_QUERIES=4
SEMANTIC_QUERY_EXPANSION_AGENT_NAME=semantic_query_expander

SEMANTIC_MEMORY_ENABLED=false
SEMANTIC_CANDIDATE_SCORING_ENABLED=false
SEMANTIC_FAIL_OPEN=true
SEMANTIC_TOP_K=4
EMBEDDING_PROVIDER=lmstudio
EMBEDDING_MODEL=text-embedding-qwen3-embedding-8b
EMBEDDING_BATCH_SIZE=32

# --- Firecrawl (optional article extraction fallback) ---
# Used only if local extractors cannot recover enough article content.
# https://docs.firecrawl.dev/
FIRECRAWL_API_KEY=
