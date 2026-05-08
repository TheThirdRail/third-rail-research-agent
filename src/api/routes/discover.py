"""Discovery API routes."""

from fastapi import APIRouter
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from src.services import DiscoveryService

router = APIRouter()


class DiscoverRequest(BaseModel):
    """Request model for story discovery."""

    topics: list[str] | None = None


class DiscoverResponse(BaseModel):
    """Response model for story discovery."""

    topics_searched: list[str]
    raw_output: str


@router.post("/discover", response_model=DiscoverResponse)
async def discover_stories(request: DiscoverRequest) -> DiscoverResponse:
    """Discover relevant stories based on topics.

    If no topics are provided, uses the channel profile.
    """
    result = await run_in_threadpool(_run_discovery_sync, request)
    return DiscoverResponse(**result)


def _run_discovery_sync(request: DiscoverRequest) -> dict:
    service = DiscoveryService()
    return service.discover(request.topics)
