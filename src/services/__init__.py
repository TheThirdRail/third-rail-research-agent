"""Application services for Research Agent.

Services encapsulate business logic and orchestration,
providing a clean interface for both CLI and API consumers.
"""

from src.services.analysis_service import AnalysisService
from src.services.balanced_source_planner import BalancedSourcePlanner
from src.services.discovery_service import DiscoveryService
from src.services.duplicate_detector import check_duplicate
from src.services.narrative_analyzer_service import NarrativeAnalyzerService
from src.services.relevance_scorer_service import RelevanceScorerService
from src.services.report_renderer import ReportRenderer
from src.services.rss_fallback_service import RssFallbackService
from src.services.source_registry import SourceRegistry, get_source_registry
from src.services.source_scoring import score_candidate
from src.services.story_parser_service import StoryParserService

__all__ = [
    "AnalysisService",
    "BalancedSourcePlanner",
    "DiscoveryService",
    "NarrativeAnalyzerService",
    "RelevanceScorerService",
    "ReportRenderer",
    "RssFallbackService",
    "SourceRegistry",
    "StoryParserService",
    "check_duplicate",
    "get_source_registry",
    "score_candidate",
]
