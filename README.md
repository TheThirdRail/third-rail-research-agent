# Research Agent

> AI-powered news research and political bias analysis for YouTube content creators

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![CrewAI](https://img.shields.io/badge/framework-CrewAI-green.svg)](https://crewai.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

Research Agent is a multi-agent AI system that helps YouTube content creators:

- **Discover stories** relevant to their channel's focus areas
- **Aggregate sources** from across the political spectrum
- **Classify bias** on a granular 9-point scale (-4 to +4)
- **Separate facts from opinions** across all sources
- **Generate reports** with structured outlines for video production
- **Learn from performance** to improve recommendations over time

## Features

### 🔍 Story Discovery
- RSS feed aggregation from 15+ curated news sources
- DuckDuckGo web search (no API key required)
- Keyword-based relevance ranking
- Performance prediction based on historical data

### 📊 Bias Analysis
- 9-point political bias scale
- Local MBFC dataset (3,500+ sources)
- LLM-based classification for unknown sources
- Special handling for libertarian/independent media

### 📝 Report Generation
- Comprehensive multi-source analysis
- Facts vs. opinions separation
- Mainstream vs. alternative narratives
- Video outline with talking points
- Markdown + JSON output formats

### 💡 Learning System
- Track YouTube performance (views, likes, retention)
- Improve story recommendations over time
- Identify what resonates with your audience

## Installation

### Prerequisites

- Python 3.11+
- Node.js 20+ (for web UI)
- OpenRouter API key (free tier available)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/research-agent.git
cd research-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Copy environment template
cp .env.example .env
# Edit .env and add your OpenRouter API key

# Run the CLI
research-agent --help
```

### Web UI Setup

```bash
# Navigate to web directory
cd web

# Install dependencies
npm install

# Start development server
npm run dev
```

## Usage

### CLI Commands

```bash
# Discover 10 stories for your channel
research-agent discover

# Analyze a specific story by URL
research-agent analyze --url "https://example.com/article"

# Analyze a story by description
research-agent analyze --describe "State of emergency declared in Texas over border"

# View past reports
research-agent report list

# Add YouTube performance data
research-agent performance add --story-id <id> --views 50000 --likes 2500
```

### Configuration

Edit `config/channel_profile.yaml` to customize:

- Your channel's topic focus areas
- Preferred source types
- Political worldview for perspective suggestions
- Story ranking weights

## Tech Stack

| Component | Technology |
|-----------|------------|
| Agent Framework | CrewAI |
| LLM Router | LiteLLM |
| Primary LLM | OpenRouter (free tier) |
| Database | SQLite |
| Backend API | FastAPI |
| Frontend | Next.js 15 + shadcn/ui |
| CLI | Click + Rich |

## Project Structure

```
research-agent/
├── src/
│   ├── agents/         # CrewAI agent definitions
│   ├── crews/          # Crew orchestration
│   ├── tools/          # Custom tools (RSS, search, extraction)
│   ├── database/       # SQLAlchemy models
│   ├── api/            # FastAPI backend
│   └── cli/            # CLI commands
├── web/                # Next.js frontend
├── config/             # Configuration files
├── data/               # Local datasets
└── tests/              # Test suite
```

## Documentation

- [Product Requirements](prd.md) - Goals, user stories, technical specs
- [Implementation Checklist](checklist.md) - Development phases and tasks
- [Project Rules](project_rules.md) - Coding conventions and patterns

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [CrewAI](https://crewai.com) for the multi-agent framework
- [Media Bias/Fact Check](https://mediabiasfactcheck.com) for bias data
- [OpenRouter](https://openrouter.ai) for free LLM access
