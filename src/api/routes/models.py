from fastapi import APIRouter, Query

from src.services.model_service import ModelInfo, ModelService

router = APIRouter(prefix="/models", tags=["Models"])


@router.get("", response_model=list[ModelInfo])
async def list_models(
    provider: str = Query(
        ..., description="The LLM provider (e.g., openai, openrouter)"
    ),
):
    """List available models for a specific provider with pricing."""
    service = ModelService()
    return await service.get_models(provider)
