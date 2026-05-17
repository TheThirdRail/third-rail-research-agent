from fastapi import APIRouter, Depends, Query

from src.api.dependencies import require_admin_api_key
from src.services.model_service import ModelInfo, ModelService

router = APIRouter(prefix="/models", tags=["Models"])


@router.get(
    "",
    response_model=list[ModelInfo],
    dependencies=[Depends(require_admin_api_key)],
)
async def list_models(
    provider: str = Query(
        ..., description="The LLM provider (e.g., openai, openrouter)"
    ),
    refresh: bool = Query(False, description="Bypass cache and refetch models"),
):
    """List available models for a specific provider with pricing."""
    service = ModelService()
    return await service.get_models(provider, refresh=refresh)
