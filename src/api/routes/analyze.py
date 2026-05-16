"""Analysis API routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from src.api.dependencies import require_admin_api_key, require_expensive_endpoint_slot
from src.core.exceptions import (
    BudgetExceededError,
    RateLimitExceededError,
    SourceExtractionError,
    is_upstream_rate_limit_error,
)
from src.schemas.analysis_options import AnalysisOptions
from src.services import AnalysisService

logger = logging.getLogger(__name__)

router = APIRouter()


class AnalyzeRequest(BaseModel):
    """Request model for story analysis."""

    description: str
    url: str | None = None
    options: AnalysisOptions | None = None


class AnalyzeResponse(BaseModel):
    """Response model for story analysis."""

    story_id: str
    report: str
    status: str
    source_count: int | None = None
    bias_spread_met: bool | None = None
    left_source_count: int | None = None
    right_source_count: int | None = None


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    dependencies=[
        Depends(require_admin_api_key),
        Depends(require_expensive_endpoint_slot),
    ],
)
async def analyze_story(request: AnalyzeRequest) -> AnalyzeResponse:
    """Analyze a story and generate a multi-source report.

    Aggregates sources from across the political spectrum,
    classifies bias, and generates a comprehensive report.
    """
    try:
        result = await run_in_threadpool(_run_analysis_sync, request)
        return AnalyzeResponse(**result)
    except SourceExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RateLimitExceededError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    except BudgetExceededError as e:
        raise HTTPException(status_code=402, detail=str(e)) from e
    except Exception as e:
        if is_upstream_rate_limit_error(e):
            logger.warning("Upstream rate limit hit during analysis: %s", e)
            raise HTTPException(
                status_code=429,
                detail="Upstream provider rate limit exceeded. Check server logs for details.",
            ) from e
        logger.exception("Analysis failed")
        raise HTTPException(
            status_code=500,
            detail="Analysis failed. Check server logs for details.",
        ) from e


def _run_analysis_sync(request: AnalyzeRequest) -> dict[str, Any]:
    with AnalysisService() as service:
        if request.options is None:
            return service.analyze(request.description, request.url)
        return service.analyze(request.description, request.url, options=request.options)


@router.get("/analysis/{story_id}")
def get_analysis(story_id: str) -> dict:
    """Retrieve existing analysis for a story."""
    with AnalysisService() as service:
        result = service.get_analysis(story_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result


@router.get("/analysis/{story_id}/diagnostics")
def get_analysis_diagnostics(story_id: str) -> dict:
    """Retrieve persisted retrieval and analysis diagnostics for a story."""
    with AnalysisService() as service:
        result = service.get_diagnostics(story_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis diagnostics not found")
    return result


@router.get("/analysis/{story_id}/handoff/{stage}")
def get_analysis_handoff(story_id: str, stage: str) -> dict:
    """Retrieve a persisted handoff bundle for a story and stage."""
    with AnalysisService() as service:
        result = service.get_handoff(story_id, stage)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis handoff not found")
    return result
