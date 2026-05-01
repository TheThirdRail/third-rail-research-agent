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
from src.services.screenshot_capture_service import ScreenshotCaptureService
from src.services.semantic_memory_service import SemanticMemoryService
from src.services.semantic_query_expansion_service import SemanticQueryExpansionService
from src.services.social_post_resolver_service import SocialPostResolverService
from src.services.source_registry import SourceRegistry, get_source_registry
from src.services.source_scoring import score_candidate
from src.services.story_parser_service import StoryParserService
from src.services.visual_evidence_service import VisualEvidenceService

__all__ = [
    "AnalysisService",
    "BalancedSourcePlanner",
    "DiscoveryService",
    "NarrativeAnalyzerService",
    "RelevanceScorerService",
    "ReportRenderer",
    "VisualEvidenceService",
    "RssFallbackService",
    "ScreenshotCaptureService",
    "SemanticMemoryService",
    "SemanticQueryExpansionService",
    "SocialPostResolverService",
    "SourceRegistry",
    "StoryParserService",
    "check_duplicate",
    "get_source_registry",
    "score_candidate",
]
