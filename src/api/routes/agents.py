from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.agents.config import AGENT_ROLES
from src.database.session import get_db
from src.services.agent_config_service import AgentConfigService

router = APIRouter(prefix="/agents", tags=["Agents"])


class AgentConfigUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    budget_limit: float | None = None


class AgentInfo(BaseModel):
    name: str
    role: str
    goal: str
    config: dict | None = None


@router.get("", response_model=list[AgentInfo])
def list_agents(db: Session = Depends(get_db)):
    """List all available agents and their configurations."""
    service = AgentConfigService(db)
    agents = []

    for name, role_info in AGENT_ROLES.items():
        config = service.get_config(name)
        # Always return a config dict, even if empty
        config_dict = {
            "agent_name": name,
            "provider": config.provider if config else None,
            "model": config.model if config else None,
            "temperature": config.temperature if config else None,
            "budget_limit": config.budget_limit if config else None,
        }

        agents.append(
            AgentInfo(
                name=name,
                role=role_info["role"],
                goal=role_info["goal"],
                config=config_dict,
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
    config = service.get_config(name)

    # Always return a config dict, even if empty
    config_dict = {
        "agent_name": name,
        "provider": config.provider if config else None,
        "model": config.model if config else None,
        "temperature": config.temperature if config else None,
        "budget_limit": config.budget_limit if config else None,
    }

    return AgentInfo(
        name=name,
        role=role_info["role"],
        goal=role_info["goal"],
        config=config_dict,
    )


@router.post("/{name}/config")
def update_agent_config(
    name: str, config: AgentConfigUpdate, db: Session = Depends(get_db)
):
    """Update agent configuration."""
    if name not in AGENT_ROLES:
        raise HTTPException(status_code=404, detail="Agent not found")

    service = AgentConfigService(db)
    updated = service.set_config(
        agent_name=name,
        provider=config.provider,
        model=config.model,
        temperature=config.temperature,
        budget_limit=config.budget_limit,
    )

    return {
        "success": True,
        "agent": name,
        "config": {
            "provider": updated.provider,
            "model": updated.model,
            "temperature": updated.temperature,
            "budget_limit": updated.budget_limit,
        },
    }
