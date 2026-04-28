from sqlalchemy.orm import Session

from src.database.models import AgentConfiguration


class AgentConfigService:
    """Service for managing agent configurations."""

    def __init__(self, db: Session):
        self.db = db

    def get_config(self, agent_name: str) -> AgentConfiguration | None:
        """Get configuration for a specific agent."""
        return (
            self.db.query(AgentConfiguration)
            .filter(AgentConfiguration.agent_name == agent_name)
            .first()
        )

    def set_config(
        self,
        agent_name: str,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        budget_limit: float | None = None,
        free_tier: bool | None = None,
        reasoning_effort: str | None = None,
        clear_reasoning_effort: bool = False,
    ) -> AgentConfiguration:
        """Set or update configuration for an agent."""
        config = self.get_config(agent_name)
        if not config:
            config = AgentConfiguration(agent_name=agent_name)
            self.db.add(config)

        if provider is not None:
            config.provider = provider
        if model is not None:
            config.model = model
        if temperature is not None:
            config.temperature = temperature
        if budget_limit is not None:
            config.budget_limit = budget_limit
        if free_tier is not None:
            config.free_tier = free_tier
        if reasoning_effort is not None:
            config.reasoning_effort = reasoning_effort
        elif clear_reasoning_effort:
            config.reasoning_effort = None

        self.db.commit()
        self.db.refresh(config)
        return config

    def list_configs(self) -> list[AgentConfiguration]:
        """List all agent configurations."""
        return self.db.query(AgentConfiguration).all()
