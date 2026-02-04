---
name: overview
description: |
  Project overview including tech stack, dependencies, and project structure.
  This is loaded always for context about the project.
activation: always_on
---

<rule name="project-overview" version="2.0.0">
  <metadata>
    <project>Research Agent</project>
    <updated>2026-01-31</updated>
  </metadata>

  <technology_stack>
    <core>
      <item name="Language">Python 3.11+</item>
      <item name="Agent Framework">CrewAI 0.95.0+</item>
      <item name="LLM Router">LiteLLM (multi-provider: OpenRouter, Gemini, Anthropic, Groq, etc.)</item>
      <item name="Database">SQLite via SQLAlchemy 2.0</item>
      <item name="Backend API">FastAPI 0.115+</item>
      <item name="Frontend">Next.js 15 + shadcn/ui + Tailwind</item>
      <item name="CLI">Click + Rich</item>
      <item name="Container">Docker + docker-compose</item>
    </core>
  </technology_stack>

  <dependencies>
    <section name="Core">
      <dep>crewai>=0.95.0</dep>
      <dep>crewai-tools>=0.14.0</dep>
      <dep>litellm>=1.50.0</dep>
      <dep>openai>=1.0.0</dep>
    </section>
    <section name="News & Web">
      <dep>feedparser>=6.0.0</dep>
      <dep>ddgs>=6.0.0</dep>
      <dep>trafilatura>=1.12.0</dep>
      <dep>newspaper4k>=0.9.0</dep>
    </section>
    <section name="Database & API">
      <dep>sqlalchemy>=2.0.0</dep>
      <dep>fastapi>=0.115.0</dep>
      <dep>uvicorn>=0.32.0</dep>
      <dep>pydantic>=2.10.0</dep>
    </section>
    <section name="CLI">
      <dep>click>=8.1.0</dep>
      <dep>rich>=13.9.0</dep>
    </section>
  </dependencies>

  <project_structure>
    <![CDATA[
research-agent/
├── src/
│   ├── agents/         # CrewAI agent definitions
│   ├── crews/          # CrewAI crew orchestration
│   ├── tools/          # Custom CrewAI tools
│   ├── database/       # SQLAlchemy models & utils
│   ├── api/            # FastAPI backend
│   │   └── routes/     # API route handlers
│   ├── cli/            # Click CLI commands
│   ├── templates/      # Report templates
│   └── core/           # Shared utilities
│       ├── config.py       # Pydantic settings
│       └── llm_provider.py # LiteLLM router (9 providers)
├── web/                # Next.js frontend
├── config/             # YAML configuration files
├── data/               # SQLite DB & local datasets
├── tests/              # Test suite
├── Dockerfile          # Python backend image
├── docker-compose.yml  # Multi-service stack
├── .env.example        # Environment template (9 providers)
├── pyproject.toml      # Python project config
├── prd.md              # Product requirements
├── checklist.md        # Implementation checklist
└── README.md           # Project documentation
    ]]>
  </project_structure>
</rule>
