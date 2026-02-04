---
name: project-rules
description: |
  Research Agent project rules covering the multi-provider LLM architecture,
  Docker containerization, CrewAI agent patterns, and coding conventions.
  This is the master project rules file - other rule files provide detail.
activation: always_on
---

<rule name="research-agent-project" version="2.0.0">
  <metadata>
    <category>project-specific</category>
    <severity>error</severity>
    <updated>2026-01-31</updated>
  </metadata>

  <project_overview>
    <name>Research Agent</name>
    <description>AI-powered news research for YouTube creators with multi-source bias analysis</description>
    <tech_stack>
      <language>Python 3.11+</language>
      <framework>CrewAI + FastAPI</framework>
      <llm>LiteLLM (multi-provider)</llm>
      <database>SQLite + SQLAlchemy</database>
      <frontend>Next.js 15 + shadcn/ui</frontend>
      <container>Docker + docker-compose</container>
    </tech_stack>
  </project_overview>

  <llm_providers>
    <description>Uses LiteLLM to support 9 LLM providers through a unified interface</description>
    <supported>
      <provider name="openrouter" env="OPENROUTER_API_KEY" free="true"/>
      <provider name="gemini" env="GOOGLE_API_KEY" free="true"/>
      <provider name="anthropic" env="ANTHROPIC_API_KEY" free="false"/>
      <provider name="groq" env="GROQ_API_KEY" free="true"/>
      <provider name="openai" env="OPENAI_API_KEY" free="false"/>
      <provider name="grok" env="XAI_API_KEY" free="false"/>
      <provider name="cerebras" env="CEREBRAS_API_KEY" free="true"/>
      <provider name="sambanova" env="SAMBANOVA_API_KEY" free="true"/>
      <provider name="ollama" env="OLLAMA_BASE_URL" free="true"/>
    </supported>
    <usage>
      <must>Use LLMRouter from src/core/llm_provider.py</must>
      <must>Never hardcode provider-specific logic in agents</must>
      <must>Configure provider via LLM_PROVIDER env variable</must>
    </usage>
  </llm_providers>

  <conventions>
    <python>
      <formatter>Ruff</formatter>
      <linter>Ruff</linter>
      <type_checker>mypy (strict)</type_checker>
      <docstrings>Google-style</docstrings>
      <line_length>88</line_length>
    </python>
    <crewai>
      <agents>Define in src/agents/ with role/goal/backstory</agents>
      <tools>Define in src/tools/ as BaseTool subclasses</tools>
      <crews>Define in src/crews/ with task sequences</crews>
    </crewai>
    <api>
      <framework>FastAPI with Pydantic models</framework>
      <routes>src/api/routes/ with router pattern</routes>
      <cors>Allow localhost:3000 for frontend</cors>
    </api>
  </conventions>

  <constraints>
    <must>Run tests before commit: pytest tests/</must>
    <must>Use type hints on all functions</must>
    <must>Never commit .env files</must>
    <must>Use Docker for deployment</must>
    <must_not>Hardcode API keys in source code</must_not>
    <must_not>Use synchronous operations in FastAPI routes</must_not>
  </constraints>

  <related_rules>
    <rule file="overview.md">Tech stack and dependencies</rule>
    <rule file="python.md">Python coding conventions</rule>
    <rule file="crew-ai.md">CrewAI agent patterns</rule>
    <rule file="back-end.md">Database, API, CLI patterns</rule>
    <rule file="front-end.md">Next.js and shadcn conventions</rule>
    <rule file="quality-control.md">Testing and error handling</rule>
  </related_rules>
</rule>
