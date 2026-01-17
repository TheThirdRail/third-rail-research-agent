---
trigger: model_decision
description: Rules for Crew AI
---

# Project Rules: CrewAI Patterns

---

## Agent Definition Pattern

```python
from crewai import Agent
from src.core.config import settings

def create_bias_classifier_agent() -> Agent:
    """Create the bias classification agent."""
    return Agent(
        role="Political Bias Analyst",
        goal="Classify news sources on a 9-point political bias scale",
        backstory="""You are a media analyst with decades of experience 
        studying political bias in journalism. You can identify subtle 
        framing, loaded language, and partisan slant with high accuracy.
        You remain objective and base classifications on evidence.""",
        tools=[BiasClassifierTool(), ArticleExtractorTool()],
        llm=settings.default_llm,
        verbose=settings.debug,
        allow_delegation=False,
    )
```

---

## Tool Definition Pattern

```python
from crewai_tools import BaseTool
from pydantic import Field

class BiasClassifierTool(BaseTool):
    """Tool for classifying political bias of news sources."""
    
    name: str = "Bias Classifier"
    description: str = """Classifies a news source on a 9-point political 
    bias scale from -4 (far left) to +4 (far right). Provide either a 
    domain name or article text for analysis."""
    
    def _run(self, source_domain: str = "", article_text: str = "") -> str:
        """Execute bias classification."""
        # Implementation
        ...
```

---

## Crew Definition Pattern

```python
from crewai import Crew, Process
from src.agents import create_all_analysis_agents
from src.tasks import create_analysis_tasks

def create_analysis_crew() -> Crew:
    """Create the analysis crew for story research."""
    agents = create_all_analysis_agents()
    tasks = create_analysis_tasks(agents)
    
    return Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        memory=True,
    )
```

---

## LLM Configuration

Primary: OpenRouter free tier via LiteLLM

```python
from litellm import completion

# Use free OpenRouter models
response = completion(
    model="openrouter/meta-llama/llama-4-maverick:free",
    messages=[{"role": "user", "content": prompt}]
)
```

Fallback: Ollama (optional, for offline use)

```python
response = completion(
    model="ollama/llama3.1:8b",
    messages=[{"role": "user", "content": prompt}]
)
```
