"""Analysis API routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.exceptions import (
    BudgetExceededError,
    RateLimitExceededError,
    SourceExtractionError,
    is_upstream_rate_limit_error,
)
from src.core.config import settings
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
    source_count: int | None = None
    bias_spread_met: bool | None = None
    left_source_count: int | None = None
    right_source_count: int | None = None


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_story(request: AnalyzeRequest) -> AnalyzeResponse:
    """Analyze a story and generate a multi-source report.

    Aggregates sources from across the political spectrum,
    classifies bias, and generates a comprehensive report.
    """
    try:
        service = AnalysisService()
        result = service.analyze(request.description, request.url)
        return AnalyzeResponse(**result)
    except SourceExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RateLimitExceededError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    except BudgetExceededError as e:
        raise HTTPException(status_code=402, detail=str(e)) from e
    except Exception as e:
        if is_upstream_rate_limit_error(e):
            fallback_enabled = (
                settings.lmstudio_fallback_enabled and bool(settings.lmstudio_fallback_model)
            )
            fallback_note = (
                "LM Studio fallback is enabled; request still failed."
                if fallback_enabled
                else "LM Studio fallback is disabled."
            )
            raise HTTPException(
                status_code=429,
                detail=f"Upstream provider rate limit exceeded. {fallback_note} Original error: {e}",
            ) from e
        # Catch-all for other errors (keys, providers, etc)
        raise HTTPException(
            status_code=500, detail=f"Internal Analysis Error: {str(e)}"
        ) from e


@router.get("/analysis/{story_id}")
def get_analysis(story_id: str) -> dict:
    """Retrieve existing analysis for a story."""
    service = AnalysisService()
    result = service.get_analysis(story_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result
