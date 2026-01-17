# Research Agent - Implementation Checklist

**Project:** Research Agent  
**Created:** January 16, 2026  
**Status:** Planning Complete  

---

## Phase 1: Project Foundation (Week 1)

### 1.1 Project Setup
- [x] Create project directory structure
- [x] Initialize Python virtual environment
- [x] Create `pyproject.toml` with dependencies
- [x] Create `.gitignore` for Python projects
- [x] Initialize git repository
- [x] Create `README.md` with project overview

### 1.2 Configuration System
- [x] Create `config/` directory
- [x] Create `config/settings.py` with Pydantic settings
- [x] Create `config/channel_profile.yaml` template
- [x] Create `config/bias_sources.yaml` with known source ratings
- [x] Create `config/rss_feeds.yaml` curated feed list
- [x] Implement environment variable loading (.env support)

### 1.3 Database Setup
- [x] Create `src/database/` directory
- [x] Create SQLAlchemy models for Story, Source, Analysis, Performance
- [x] Create database initialization script
- [ ] Create migration system (Alembic or simple versioning)
- [x] Create database CRUD utilities
- [ ] Test database operations

### 1.4 Bias Dataset Integration
- [ ] Download MBFC dataset from GitHub
- [ ] Download Kaggle political bias dataset
- [x] Create `data/` directory for datasets
- [x] Create `LocalBiasDatabase` class for querying
- [x] Implement domain normalization
- [ ] Test bias lookups

---

## Phase 2: Core Tools (Week 2)

### 2.1 News Aggregation Tool
- [x] Create `src/tools/rss_aggregator.py`
- [x] Implement `RSSNewsAggregator` class
- [x] Add 15+ curated RSS feeds (left, center, right, libertarian)
- [x] Implement keyword filtering
- [x] Add date parsing and normalization
- [x] Create CrewAI tool wrapper

### 2.2 Web Search Tool
- [x] Create `src/tools/web_search.py`
- [x] Implement `DuckDuckGoSearchTool` using ddgs
- [x] Add news search method
- [x] Add general web search method
- [x] Implement rate limiting/politeness
- [x] Create CrewAI tool wrapper

### 2.3 Article Extraction Tool
- [x] Create `src/tools/article_extractor.py`
- [x] Implement trafilatura extraction
- [x] Implement newspaper4k fallback
- [x] Add metadata extraction (author, date, title)
- [x] Handle extraction failures gracefully
- [x] Create CrewAI tool wrapper

### 2.4 Bias Classification Tool
- [x] Create `src/tools/bias_classifier.py`
- [x] Implement local dataset lookup
- [/] Implement LLM-based classification for unknown sources
- [x] Create 9-point scale mapping
- [x] Add confidence scoring
- [x] Create CrewAI tool wrapper

### 2.5 Keyword Extraction Tool
- [x] Create `src/tools/keyword_extractor.py`
- [x] Implement YAKE extraction
- [ ] Implement KeyBERT extraction (optional, slower)
- [x] Add relevance scoring
- [x] Create CrewAI tool wrapper

### 2.6 YouTube Research Tool
- [ ] Create `src/tools/youtube_research.py`
- [ ] Implement yt-dlp search functionality
- [ ] Implement video metadata extraction
- [ ] Handle video transcript extraction (if available)
- [ ] Create CrewAI tool wrapper

---

## Phase 3: Agent Definitions (Week 3)

### 3.1 Discovery Crew Agents
- [x] Create `src/agents/` directory
- [ ] Create `profile_reader.py` - reads channel profile
- [x] Create `news_aggregator.py` - fetches news from feeds
- [ ] Create `relevance_scorer.py` - ranks stories by relevance
- [ ] Create `performance_predictor.py` - predicts audience interest

### 3.2 Analysis Crew Agents
- [ ] Create `story_parser.py` - extracts story details from input
- [x] Create `source_aggregator.py` - finds all sources for a story
- [x] Create `bias_classifier.py` - classifies source political leaning
- [x] Create `fact_extractor.py` - separates facts from opinions
- [ ] Create `narrative_analyzer.py` - identifies narratives
- [x] Create `report_writer.py` - generates final report

### 3.3 Agent Configuration
- [x] Create `src/agents/config.py` with agent settings
- [x] Implement LLM selection logic (local vs. cloud)
- [x] Add agent backstories tailored to tasks
- [x] Configure tool assignments per agent
- [ ] Test individual agent functionality

---

## Phase 4: Crew Orchestration (Week 3-4)

### 4.1 Discovery Crew
- [x] Create `src/crews/discovery_crew.py`
- [x] Define discovery task flow
- [x] Implement story collection pipeline
- [ ] Implement ranking pipeline
- [ ] Add performance data integration (if available)
- [ ] Test full discovery workflow

### 4.2 Analysis Crew
- [x] Create `src/crews/analysis_crew.py`
- [x] Define analysis task flow
- [x] Implement source collection pipeline
- [x] Implement bias classification pipeline
- [x] Implement fact extraction pipeline
- [x] Implement report generation pipeline
- [ ] Test full analysis workflow

### 4.3 Report Templates
- [ ] Create `src/templates/` directory
- [ ] Create `report_template.md` Markdown template
- [ ] Create `report_schema.json` JSON schema
- [ ] Create `outline_template.md` video outline template
- [ ] Implement template rendering
- [ ] Add libertarian perspective section

---

## Phase 5: CLI Interface (Week 4)

### 5.1 CLI Framework
- [x] Create `src/cli/` directory
- [x] Create `main.py` entry point with Click
- [x] Implement Rich console output formatting
- [x] Add progress indicators for long operations
- [x] Create help documentation

### 5.2 Discovery Commands
- [x] Implement `discover` command
- [x] Add `--topics` filter option
- [x] Add `--count` option (default 10)
- [/] Display results in formatted table
- [ ] Save results to database

### 5.3 Analysis Commands
- [x] Implement `analyze` command
- [x] Support URL input
- [x] Support description input
- [ ] Support interactive story selection from discovery
- [x] Display progress during analysis
- [ ] Auto-save to database

### 5.4 Report Commands
- [/] Implement `report` command to view past reports
- [ ] Add `--format` option (markdown/json)
- [x] Add `--output` option for file export
- [x] Implement `list` command for browsing history

### 5.5 Performance Commands
- [x] Implement `performance add` command
- [x] Allow inputting YouTube stats for a story
- [ ] Implement `performance view` command
- [ ] Implement `learn` command to trigger model retraining

---

## Phase 6: Web UI (Week 5-6)

### 6.1 FastAPI Backend
- [ ] Create `src/api/` directory
- [ ] Create `main.py` FastAPI application
- [ ] Implement `/discover` endpoint
- [ ] Implement `/analyze` endpoint
- [ ] Implement `/reports` endpoint
- [ ] Implement `/performance` endpoint
- [ ] Add WebSocket for progress updates
- [ ] Add CORS configuration

### 6.2 Next.js Frontend Setup
- [ ] Create `web/` directory
- [ ] Initialize Next.js 15 project
- [ ] Install shadcn/ui components
- [ ] Configure Tailwind CSS
- [ ] Create layout with navigation

### 6.3 Frontend Pages
- [ ] Create Dashboard page (home)
- [ ] Create Discovery page with story cards
- [ ] Create Analysis page with input form
- [ ] Create Report viewer page
- [ ] Create History/browse page
- [ ] Create Performance tracking page

### 6.4 Frontend Components
- [ ] Create StoryCard component
- [ ] Create BiasIndicator component (9-point visual)
- [ ] Create SourceMatrix component
- [ ] Create FactsComparison component
- [ ] Create ReportViewer component
- [ ] Create PerformanceInput form

### 6.5 API Integration
- [ ] Create API client service
- [ ] Implement React Query for data fetching
- [ ] Add loading states
- [ ] Add error handling
- [ ] Implement optimistic updates

---

## Phase 7: Integration & Testing (Week 6)

### 7.1 Integration Testing
- [ ] Test CLI → CrewAI → Database flow
- [ ] Test API → CrewAI → Database flow
- [ ] Test Web UI → API → CrewAI flow
- [ ] Test all tool integrations
- [ ] Test error handling and recovery

### 7.2 Quality Assurance
- [ ] Create test channel profile
- [ ] Run discovery on 5 different topic combinations
- [ ] Run analysis on 3 different stories
- [ ] Verify bias classifications against known sources
- [ ] Verify report quality and completeness

### 7.3 Performance Testing
- [ ] Measure discovery workflow time
- [ ] Measure analysis workflow time
- [ ] Identify bottlenecks
- [ ] Optimize slow operations
- [ ] Test with large source counts (20+ sources)

---

## Phase 8: Documentation & Polish (Week 7)

### 8.1 User Documentation
- [ ] Update README.md with full usage instructions
- [ ] Create QUICKSTART.md for new users
- [ ] Document all CLI commands with examples
- [ ] Document API endpoints
- [ ] Create FAQ document

### 8.2 Developer Documentation
- [ ] Document project structure
- [ ] Document tool creation process
- [ ] Document agent customization
- [ ] Create CONTRIBUTING.md

### 8.3 Configuration Documentation
- [ ] Document channel profile setup
- [ ] Document RSS feed customization
- [ ] Document bias dataset updates
- [ ] Document LLM configuration options

### 8.4 Final Polish
- [ ] Review and clean up all code
- [ ] Add comprehensive error messages
- [ ] Ensure consistent logging
- [ ] Create sample outputs for documentation
- [ ] Final end-to-end testing

---

## Phase 9: Learning System (Week 8+)

### 9.1 Performance Data Collection
- [ ] Finalize YouTube stats input format
- [ ] Create performance history views
- [ ] Calculate engagement metrics

### 9.2 Recommendation Engine
- [ ] Analyze historical performance patterns
- [ ] Identify high-performing story characteristics
- [ ] Implement weighted relevance scoring
- [ ] A/B test recommendations vs. baseline

### 9.3 Continuous Improvement
- [ ] Create feedback mechanism
- [ ] Allow manual bias corrections
- [ ] Track classification accuracy over time
- [ ] Implement model fine-tuning (if using local LLM)

---

## Milestone Summary

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| Phase 1: Foundation | Week 1 | [ ] Not Started |
| Phase 2: Core Tools | Week 2 | [ ] Not Started |
| Phase 3: Agents | Week 3 | [ ] Not Started |
| Phase 4: Crews | Week 3-4 | [ ] Not Started |
| Phase 5: CLI | Week 4 | [ ] Not Started |
| Phase 6: Web UI | Week 5-6 | [ ] Not Started |
| Phase 7: Testing | Week 6 | [ ] Not Started |
| Phase 8: Docs | Week 7 | [ ] Not Started |
| Phase 9: Learning | Week 8+ | [ ] Not Started |

---

## Quick Reference: Priority Tasks for MVP

The minimum tasks needed for a working CLI version:

1. [ ] Project setup + dependencies
2. [ ] Database models + initialization
3. [ ] RSS aggregator tool
4. [ ] Web search tool (ddgs)
5. [ ] Article extractor tool
6. [ ] Bias classifier tool (local dataset + LLM)
7. [ ] Discovery crew (basic)
8. [ ] Analysis crew (basic)
9. [ ] Report writer agent
10. [ ] CLI `discover` and `analyze` commands
