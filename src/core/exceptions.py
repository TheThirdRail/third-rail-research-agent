"""Custom exceptions for Research Agent."""


class ResearchAgentError(Exception):
    """Base exception for Research Agent."""

    pass


class ConfigurationError(ResearchAgentError):
    """Configuration or environment error."""

    pass


class SourceExtractionError(ResearchAgentError):
    """Failed to extract content from a source."""

    pass


class BiasClassificationError(ResearchAgentError):
    """Failed to classify source bias."""

    pass


class CrewExecutionError(ResearchAgentError):
    """CrewAI crew failed to complete."""

    pass


class DatabaseError(ResearchAgentError):
    """Database operation failed."""

    pass


class RateLimitError(ResearchAgentError):
    """Rate limit exceeded on external service."""

    pass
