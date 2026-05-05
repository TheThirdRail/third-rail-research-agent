# Research Agent - Product Requirements Document (PRD)

**Project Name:** Research Agent  
**Version:** 1.0  
**Date:** January 16, 2026  
**Author:** AI Architect  

---

## 1. Executive Summary

Research Agent is an agentic AI system designed to help a libertarian YouTube content creator efficiently research news stories, analyze political bias across multiple sources, separate facts from opinions, and generate structured content outlines. The system uses CrewAI for multi-agent orchestration, free/local LLMs for cost efficiency, and provides both CLI and web interfaces.

---

## 2. Goals and Objectives

### Primary Goals

1. **Automate news research** - Find relevant stories across the creator's topic areas without manual searching
2. **Multi-source bias analysis** - Aggregate coverage from sources across the political spectrum and classify each on a 9-point scale
3. **Fact vs. opinion separation** - Clearly distinguish verifiable facts from editorial interpretations
4. **Content preparation** - Generate structured outlines that present facts first, then opinion analysis
5. **Performance learning** - Track which story types perform well with the audience over time

### Success Metrics

- Reduce story research time by 70%+
- Achieve 85%+ accuracy in bias classification
- Generate reports that require minimal manual editing
- Build a performance database that improves story recommendations over time

---

## 3. Target User Profile

### Creator Profile

| Attribute | Value |
|-----------|-------|
| **Platform** | YouTube |
| **Worldview** | Libertarian (Ron Paul, Dave Smith, Thomas Massie style) |
| **Content Style** | Facts first, clearly labeled opinion afterward |
| **Primary Topics** | US national politics, geopolitics, conspiracy theories, news, cultural issues, spirituality/religion, tech, political commentators |
| **Secondary Topics** | Florida local politics, online debates |
| **Publishing Cadence** | On-demand (not scheduled) |

### Key Needs

1. Present facts neutrally before adding personal interpretation
2. Cover stories from multiple political perspectives
3. Identify mainstream media narratives vs. alternative viewpoints
4. Track what resonates with audience

---

## 4. User Stories

### Epic 1: Story Discovery

| ID | User Story | Priority |
|----|------------|----------|
| US-1.1 | As a creator, I want the system to find 10 relevant stories based on my channel's topics so I can choose one to cover | P0 |
| US-1.2 | As a creator, I want stories ranked by predicted audience interest based on past performance | P1 |
| US-1.3 | As a creator, I want to filter discovered stories by topic category | P1 |
| US-1.4 | As a creator, I want to see why each story was selected (relevance reasoning) | P2 |

### Epic 2: Specific Story Analysis

| ID | User Story | Priority |
|----|------------|----------|
| US-2.1 | As a creator, I want to input a story URL or description and get full multi-source analysis | P0 |
| US-2.2 | As a creator, I want to input a YouTube video URL about a story and have the system research it | P1 |
| US-2.3 | As a creator, I want to describe a story in my own words and have the system find coverage | P0 |

### Epic 3: Source Aggregation & Bias Analysis

| ID | User Story | Priority |
|----|------------|----------|
| US-3.1 | As a creator, I want the system to find as many sources as possible covering a story | P0 |
| US-3.2 | As a creator, I want each source classified on a 9-point political bias scale | P0 |
| US-3.3 | As a creator, I want to see which facts are agreed upon across all sources | P0 |
| US-3.4 | As a creator, I want to see which facts are reported by only one side | P0 |
| US-3.5 | As a creator, I want opinions clearly separated from facts for each source | P0 |
| US-3.6 | As a creator, I want to identify mainstream narratives vs. alternative takes | P1 |

### Epic 4: Report Generation

| ID | User Story | Priority |
|----|------------|----------|
| US-4.1 | As a creator, I want a comprehensive report with all data points organized clearly | P0 |
| US-4.2 | As a creator, I want an outline with bullet points for my video | P0 |
| US-4.3 | As a creator, I want suggestions for how to approach the story from my libertarian perspective | P1 |
| US-4.4 | As a creator, I want reports in both Markdown (readable) and JSON (structured) formats | P0 |

### Epic 5: Performance Tracking & Learning

| ID | User Story | Priority |
|----|------------|----------|
| US-5.1 | As a creator, I want to attach my YouTube stats (views, likes, retention) to past analyses | P1 |
| US-5.2 | As a creator, I want the system to learn which story types perform well | P1 |
| US-5.3 | As a creator, I want recommendations weighted by historical audience response | P2 |

### Epic 6: Interface & Deployment

| ID | User Story | Priority |
|----|------------|----------|
| US-6.1 | As a creator, I want to use the system via CLI in my terminal or IDE | P0 |
| US-6.2 | As a creator, I want a web interface for visual interaction | P0 |
| US-6.3 | As a creator, I want all past analyses stored for future reference | P1 |

---

## 5. 9-Point Political Bias Scale

The system uses a granular 9-point scale for political classification:

| Value | Label | Description | Example Sources |
|-------|-------|-------------|-----------------|
| -4 | **Far Left** | Extreme progressive, socialist framing | Jacobin, TruthOut |
| -3 | **Left** | Strong liberal/Democratic perspective | MSNBC, HuffPost |
| -2 | **Lean Left** | Moderate liberal tendency | CNN, NYT, WaPo |
| -1 | **Slight Left** | Minor left-leaning indicators | NPR, BBC |
| 0 | **Center** | Balanced, neutral reporting | Reuters, AP, C-SPAN |
| +1 | **Slight Right** | Minor right-leaning indicators | The Hill, RealClearPolitics |
| +2 | **Lean Right** | Moderate conservative tendency | WSJ Editorial, NY Post |
| +3 | **Right** | Strong conservative/Republican perspective | Fox News, Daily Wire |
| +4 | **Far Right** | Extreme nationalist/populist framing | Breitbart, Gateway Pundit |

### Additional Classification: Libertarian Sources

Since the creator is libertarian, special attention to sources that may not fit the left-right spectrum:

| Category | Example Sources |
|----------|-----------------|
| **Libertarian** | Reason, Mises Institute, Tom Woods, Part of the Problem (Dave Smith) |
| **Anti-Establishment** | The Intercept, Glenn Greenwald, Matt Taibbi |
| **Alternative Media** | Joe Rogan, Tim Pool, Breaking Points |

---

## 6. Technical Requirements

### 6.1 Core Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Agent Framework** | CrewAI 0.95+ | Role-based multi-agent orchestration |
| **LLM Router** | LiteLLM | Unified interface for model switching |
| **Primary LLM** | OpenRouter (free tier) | Free Llama 4, DeepSeek, Gemma models |
| **Fallback LLM** | Ollama (local) | Optional - only if offline or rate limited |
| **News Aggregation** | feedparser + RSS | Free, no API key |
| **Web Search** | ddgs (DuckDuckGo) | Free, no API key |
| **Article Extraction** | trafilatura + newspaper4k | Free, robust extraction |
| **Keyword Analysis** | YAKE + KeyBERT | Local, no API |
| **YouTube Research** | yt-dlp | Free metadata extraction |
| **Database** | SQLite + SQLAlchemy | Simple, local, no server |
| **Backend API** | FastAPI | Async Python, OpenAPI docs |
| **Frontend** | Next.js 15 + shadcn/ui | Modern React, good DX |
| **CLI** | Click + Rich | Beautiful terminal output |

### 6.2 Free Tool Constraint

> [!IMPORTANT]
> All research tools must operate **without paid API keys**. The only exception is when the user explicitly chooses to enable a premium LLM provider.

### 6.3 OpenRouter-First Architecture

The system prioritizes free OpenRouter models:
1. OpenRouter free tier models (primary) - Llama 4, DeepSeek, Gemma
2. Local database (SQLite)
3. Local bias dataset (downloaded once)
4. Ollama (optional fallback for offline use)

---

## 7. Data Models

### 7.1 Channel Profile

```
ChannelProfile:
  - id: UUID
  - name: string
  - description: text
  - topics: string[] (e.g., ["us_politics", "geopolitics", "conspiracy"])
  - worldview: string (e.g., "libertarian")
  - created_at: timestamp
  - updated_at: timestamp
```

### 7.2 Story

```
Story:
  - id: UUID
  - title: string
  - description: text
  - keywords: string[]
  - discovered_at: timestamp
  - relevance_score: float
  - performance_prediction: float (after learning)
  - status: enum (pending, selected, analyzed, published)
```

### 7.3 Source

```
Source:
  - id: UUID
  - story_id: UUID (FK)
  - domain: string
  - url: string
  - title: string
  - author: string?
  - published_date: date?
  - full_text: text
  - political_bias: int (-4 to +4)
  - bias_confidence: float
  - factual_rating: string?
```

### 7.4 Analysis

```
Analysis:
  - id: UUID
  - story_id: UUID (FK)
  - agreed_facts: string[]
  - left_only_facts: string[]
  - right_only_facts: string[]
  - mainstream_narrative: text
  - alternative_takes: text
  - opinions_by_side: json
  - libertarian_angle: text
  - outline: text
  - created_at: timestamp
```

### 7.5 Performance Tracking

```
VideoPerformance:
  - id: UUID
  - story_id: UUID (FK)
  - youtube_video_id: string?
  - views_day_1: int
  - views_week_1: int
  - likes: int
  - comments: int
  - retention_percent: float?
  - recorded_at: timestamp
```

---

## 8. System Workflows

### Workflow A: Story Discovery Mode

```
User Request: "Find me 10 stories"
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                    DISCOVERY CREW                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Profile Reader Agent                                     │
│     └─ Reads channel profile, extracts topic keywords        │
│                                                              │
│  2. News Aggregator Agent                                    │
│     └─ Queries RSS feeds + DuckDuckGo for recent stories    │
│                                                              │
│  3. Relevance Scorer Agent                                   │
│     └─ Ranks stories by topic match + trending signals      │
│                                                              │
│  4. Performance Predictor Agent (if history exists)          │
│     └─ Adjusts rankings based on past audience response     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
Output: Top 10 stories with rankings and rationale
    │
    ▼
User selects a story → Proceeds to Analysis Crew
```

### Workflow B: Specific Story Analysis Mode

```
User Request: "Analyze this story: [URL/description]"
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                    ANALYSIS CREW                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Story Parser Agent                                       │
│     └─ Extracts story details from URL/description          │
│                                                              │
│  2. Source Aggregator Agent                                  │
│     └─ Finds all sources covering this story                │
│     └─ Extracts full article text from each                 │
│                                                              │
│  3. Bias Classifier Agent                                    │
│     └─ Classifies each source on 9-point scale              │
│     └─ Uses local dataset + LLM analysis                    │
│                                                              │
│  4. Fact Extractor Agent                                     │
│     └─ Identifies facts vs. opinions in each source         │
│     └─ Finds agreed facts, left-only, right-only            │
│                                                              │
│  5. Narrative Analyzer Agent                                 │
│     └─ Identifies mainstream narrative                       │
│     └─ Identifies alternative/counter-narratives            │
│                                                              │
│  6. Report Writer Agent                                      │
│     └─ Generates comprehensive report                        │
│     └─ Creates video outline with talking points            │
│     └─ Suggests libertarian perspective approach            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
Output: Full analysis report (Markdown + JSON) + video outline
```

---

## 9. Report Structure

### Final Report Sections

1. **Executive Summary** - 3-5 sentence overview
2. **Story Overview** - What happened, when, key players
3. **Source Matrix** - All sources with bias ratings
4. **Agreed Facts** - Facts confirmed across political spectrum
5. **Disputed Facts** - Facts reported by only one side
6. **Opinion Analysis** - What each side is saying (labeled clearly)
7. **Narrative Analysis**
   - Mainstream media narrative
   - Alternative/independent takes
   - Libertarian angle
8. **Recommended Approach** - How to cover from creator's POV
9. **Video Outline** - Bullet points for video structure
10. **Sources & Citations** - Full list with links

---

## 10. Scope Boundaries

### In Scope (v1.0)

- [x] Story discovery from RSS + DuckDuckGo
- [x] Source aggregation and content extraction
- [x] 9-point political bias classification
- [x] Fact vs. opinion separation
- [x] Report generation (Markdown + JSON)
- [x] Video outline generation
- [x] CLI interface
- [x] Local web UI
- [x] SQLite database storage
- [x] YouTube stats input for performance tracking

### Out of Scope (Future Versions)

- [ ] YouTube API integration for automatic stats
- [ ] Video script generation (beyond outline)
- [ ] Audio/video analysis of source content
- [ ] Real-time monitoring/alerts
- [ ] Multi-user support
- [ ] Cloud deployment
- [ ] Subscription/payment system

---

## 11. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Rate limiting on DuckDuckGo | Medium | Implement delays, have RSS as fallback |
| Bias classification inaccuracy | High | Use dataset + LLM hybrid approach, allow manual override |
| Article extraction failures | Medium | Try multiple extractors (trafilatura → newspaper4k → fallback) |
| LLM quality variance | Medium | Use LiteLLM for easy model switching |
| pytrends unreliability | Low | Use keyword extraction from articles instead |

---

## 12. Acceptance Criteria & Status

### Phase 1: CLI MVP (Complete)
- [x] Story discovery from RSS + web search
- [x] 9-point political bias classification
- [x] Markdown + JSON reports
- [x] SQLite database storage

### Phase 2: Hardening & Observability (Complete - Hardened P2)
- [x] LanceDB integration for semantic memory
- [x] CLI `diagnostics` and `handoff` commands
- [x] Scenario-based benchmark harness
- [x] Balanced source planner and bucket policy

### Phase 3: Web UI (In Progress)
- [x] FastAPI backend stable
- [ ] Next.js frontend (UI in development)
- [ ] Visual bias distribution charts

### Phase 4: Learning System (Planned)
- [ ] Performance data influences story recommendations
- [ ] System improves over time with more data
