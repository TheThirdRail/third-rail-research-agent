# Project Rules: Backend (Database, API, CLI)

---

## Database Conventions

### Model Pattern

```python
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Story(Base):
    __tablename__ = "stories"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    sources: Mapped[list["Source"]] = relationship(back_populates="story")
    analysis: Mapped["Analysis"] = relationship(back_populates="story", uselist=False)
```

### CRUD Pattern

```python
from sqlalchemy.orm import Session
from src.database.models import Story

class StoryCRUD:
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, title: str, description: str) -> Story:
        story = Story(title=title, description=description)
        self.db.add(story)
        self.db.commit()
        self.db.refresh(story)
        return story
    
    def get_by_id(self, story_id: UUID) -> Story | None:
        return self.db.query(Story).filter(Story.id == story_id).first()
    
    def list_recent(self, limit: int = 10) -> list[Story]:
        return self.db.query(Story).order_by(Story.created_at.desc()).limit(limit).all()
```

---

## API Conventions

### Route Organization

```python
# src/api/routes/analyze.py
from fastapi import APIRouter, HTTPException, Depends
from src.api.schemas import AnalyzeRequest, AnalysisResponse
from src.crews.analysis_crew import run_analysis

router = APIRouter(prefix="/analyze", tags=["Analysis"])

@router.post("/", response_model=AnalysisResponse)
async def analyze_story(request: AnalyzeRequest) -> AnalysisResponse:
    """Analyze a story from URL or description."""
    try:
        result = await run_analysis(
            url=request.url,
            description=request.description,
        )
        return AnalysisResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Schema Pattern

```python
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class AnalyzeRequest(BaseModel):
    url: str | None = Field(None, description="URL of story to analyze")
    description: str | None = Field(None, description="Description of story")
    
    model_config = {"extra": "forbid"}

class SourceResult(BaseModel):
    domain: str
    title: str
    political_bias: int = Field(ge=-4, le=4)
    bias_label: str
    facts: list[str]
    opinions: list[str]
    
class AnalysisResponse(BaseModel):
    id: UUID
    story_title: str
    sources: list[SourceResult]
    agreed_facts: list[str]
    disputed_facts: dict[str, list[str]]
    created_at: datetime
```

---

## CLI Conventions

### Command Structure

```python
import click
from rich.console import Console
from rich.table import Table

console = Console()

@click.group()
def cli():
    """Research Agent - AI-powered news research for content creators."""
    pass

@cli.command()
@click.option("--count", "-n", default=10, help="Number of stories to discover")
@click.option("--topics", "-t", multiple=True, help="Filter by topics")
def discover(count: int, topics: tuple[str, ...]):
    """Discover relevant stories for your channel."""
    with console.status("[bold green]Discovering stories..."):
        # Run discovery
        ...
    
    # Display results
    table = Table(title="Discovered Stories")
    table.add_column("Rank", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Score", style="green")
    # ...
    console.print(table)
```
