"""Service layer for story discovery.

Encapsulates the discovery workflow, providing a clean interface
for CLI and API consumers.
"""

import logging
from typing import Any

from src.core.config import settings
from src.crews import run_discovery
from src.tools.channel_profile_loader import channel_loader

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Service for orchestrating story discovery workflows.

    Wraps the CrewAI discovery workflow with channel profile
    integration and consistent interface.
    """

    def __init__(self) -> None:
        """Initialize discovery service."""
        pass

    def _load_channel_topics(self) -> list[str]:
        """Load topics from channel profile.

        Returns:
            List of topic keywords from profile, or defaults.
        """
        try:
            scope = channel_loader.load(settings.channel_profile_path)
            return scope.topics[:20]
        except FileNotFoundError:
            logger.warning("No channel profile found, using defaults")
            return ["politics", "geopolitics", "news"]
        except Exception as e:
            logger.warning(f"Error loading channel profile: {e}")
            return ["politics", "geopolitics", "news"]

    def discover(
        self,
        topics: list[str] | None = None,
        count: int = 10,
    ) -> dict[str, Any]:
        """Run discovery workflow to find relevant stories.

        Args:
            topics: Optional list of topic keywords. If not provided,
                loads from channel profile.

        Returns:
            Dictionary with topics_searched and raw_output.
        """
        # Get topics from args or channel profile
        topic_list = topics if topics else self._load_channel_topics()

        logger.info(f"Discovering stories for topics: {topic_list[:5]}...")

        # Run the CrewAI discovery workflow
        result = run_discovery(topic_list, count=count)

        logger.info("Discovery complete")

        return {
            "topics_searched": result.get("topics_searched", topic_list),
            "raw_output": result.get("raw_output", ""),
        }
