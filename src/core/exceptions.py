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


class RateLimitExceededError(RateLimitError):
    """Rate limit exceeded and retries exhausted."""

    pass


class BudgetExceededError(ResearchAgentError):
    """Budget limit reached for the current period."""

    pass


def is_upstream_rate_limit_error(exc: Exception) -> bool:
    """Best-effort detection for provider rate-limit failures."""
    message = str(exc).lower()
    class_name = exc.__class__.__name__.lower()
    markers = (
        "ratelimiterror",
        "rate limit",
        "rate_limited",
        "resource_exhausted",
        "too many requests",
        "429",
    )
    if any(marker in message for marker in markers):
        return True
    return "ratelimit" in class_name
