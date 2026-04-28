from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from src.agents.config import AGENT_ROLES
from src.core.config import settings
from src.core.model_normalization import (
    normalize_model_for_provider,
    normalize_provider_name,
)
from src.database.session import get_db
from src.services.agent_config_service import AgentConfigService
from src.services.model_service import ModelService

router = APIRouter(prefix="/agents", tags=["Agents"])


class AgentConfigUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    budget_limit: float | None = None
    free_tier: bool | None = None
    reasoning_effort: Literal["none", "low", "medium", "high"] | None = None


class AgentInfo(BaseModel):
    name: str
    role: str
    goal: str
    config: dict | None = None


def _config_dict(name: str, config) -> dict:
    return {
        "agent_name": name,
        "provider": config.provider if config else None,
        "model": config.model if config else None,
        "temperature": config.temperature if config else None,
        "budget_limit": config.budget_limit if config else None,
        "free_tier": config.free_tier if config else None,
        "reasoning_effort": config.reasoning_effort if config else None,
    }


@router.get("", response_model=list[AgentInfo])
def list_agents(db: Session = Depends(get_db)):
    """List all available agents and their configurations."""
    service = AgentConfigService(db)

    agents = []
    for name, role_info in AGENT_ROLES.items():
        agents.append(
            AgentInfo(
                name=name,
                role=role_info["role"],
                goal=role_info["goal"],
                config=_config_dict(name, service.get_config(name)),
            )
        )
    return agents


@router.get("/{name}", response_model=AgentInfo)
def get_agent(name: str, db: Session = Depends(get_db)):
    """Get specific agent info."""
    if name not in AGENT_ROLES:
        raise HTTPException(status_code=404, detail="Agent not found")

    role_info = AGENT_ROLES[name]
    service = AgentConfigService(db)

    return AgentInfo(
        name=name,
        role=role_info["role"],
        goal=role_info["goal"],
        config=_config_dict(name, service.get_config(name)),
    )


async def _validate_model(provider: str, model: str) -> str:
    provider = normalize_provider_name(provider) or "openrouter"
    normalized_model = normalize_model_for_provider(provider, model)

    models = await ModelService().get_models(provider)
    if not models:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot validate models for {provider}; "
                "missing API key or provider unavailable."
            ),
        )

    allowed_ids = {
        normalize_model_for_provider(provider, model_info.id)
        for model_info in models
    }
    if normalized_model not in allowed_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model '{model}' for provider '{provider}'.",
        )

    return normalized_model


@router.post("/{name}/config")
async def update_agent_config(
    name: str, config: AgentConfigUpdate, db: Session = Depends(get_db)
):
    """Update agent configuration."""
    if name not in AGENT_ROLES:
        raise HTTPException(status_code=404, detail="Agent not found")

    service = AgentConfigService(db)
    existing = await run_in_threadpool(service.get_config, name)

    provider_to_save = config.provider
    if provider_to_save is not None:
        provider_to_save = normalize_provider_name(provider_to_save)

    model_to_save = config.model
    if config.model is not None:
        provider_for_validation = (
            provider_to_save
            or (existing.provider if existing and existing.provider else None)
            or settings.llm_provider
        )
        model_to_save = await _validate_model(provider_for_validation, config.model)

    fields_set = config.model_fields_set
    reasoning_effort_to_save = config.reasoning_effort
    clear_reasoning_effort = (
        "reasoning_effort" in fields_set and config.reasoning_effort is None
    )
    if provider_to_save is not None and provider_to_save != "openai":
        reasoning_effort_to_save = None
        clear_reasoning_effort = True

    updated = await run_in_threadpool(
        service.set_config,
        agent_name=name,
        provider=provider_to_save,
        model=model_to_save,
        temperature=config.temperature,
        budget_limit=config.budget_limit,
        free_tier=config.free_tier,
        reasoning_effort=reasoning_effort_to_save,
        clear_reasoning_effort=clear_reasoning_effort,
    )

    return {
        "success": True,
        "agent": name,
        "config": {
            "provider": updated.provider,
            "model": updated.model,
            "temperature": updated.temperature,
            "budget_limit": updated.budget_limit,
            "free_tier": updated.free_tier,
            "reasoning_effort": updated.reasoning_effort,
        },
    }
