"""Analysis API routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.exceptions import BudgetExceededError
from src.services import AnalysisService

router = APIRouter()


class AnalyzeRequest(BaseModel):
    """Request model for story analysis."""

    description: str
    url: str | None = None


class AnalyzeResponse(BaseModel):
    """Response model for story analysis."""

    story_id: str
    report: str
    status: str


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_story(request: AnalyzeRequest) -> AnalyzeResponse:
    """Analyze a story and generate a multi-source report.

    Aggregates sources from across the political spectrum,
    classifies bias, and generates a comprehensive report.
    """
    try:
        service = AnalysisService()
        result = service.analyze(request.description, request.url)
        return AnalyzeResponse(**result)
    except BudgetExceededError as e:
        raise HTTPException(status_code=402, detail=str(e)) from e
    except Exception as e:
        # Catch-all for other errors (keys, providers, etc)
        raise HTTPException(
            status_code=500, detail=f"Internal Analysis Error: {str(e)}"
        ) from e


@router.get("/analysis/{story_id}")
async def get_analysis(story_id: str) -> dict:
    """Retrieve existing analysis for a story."""
    service = AnalysisService()
    result = service.get_analysis(story_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result
