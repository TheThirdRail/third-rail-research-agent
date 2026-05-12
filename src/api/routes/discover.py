"""Discovery API routes."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from src.api.dependencies import require_admin_api_key, require_expensive_endpoint_slot
from src.services import DiscoveryService

router = APIRouter()


class DiscoverRequest(BaseModel):
    """Request model for story discovery."""

    topics: list[str] | None = None


class DiscoverResponse(BaseModel):
    """Response model for story discovery."""

    topics_searched: list[str]
    raw_output: str


@router.post(
    "/discover",
    response_model=DiscoverResponse,
    dependencies=[
        Depends(require_admin_api_key),
        Depends(require_expensive_endpoint_slot),
    ],
)
async def discover_stories(request: DiscoverRequest) -> DiscoverResponse:
    """Discover relevant stories based on topics.

    If no topics are provided, uses the channel profile.
    """
    result = await run_in_threadpool(_run_discovery_sync, request)
    topics = result.get("topics_searched", [])
    return DiscoverResponse(
        topics_searched=topics if isinstance(topics, list) else [],
        raw_output=str(result.get("raw_output", "")),
    )


def _run_discovery_sync(request: DiscoverRequest) -> dict[str, object]:
    service = DiscoveryService()
    return service.discover(request.topics)
