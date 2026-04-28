"""Custom CrewAI tools for news research."""

from src.tools.article_extractor import (
    ArticleExtractor,
    ArticleExtractorTool,
    ExtractedArticle,
    MultiArticleExtractorTool,
)
from src.tools.bias_classifier import (
    BIAS_LABELS,
    BiasClassifier,
    BiasClassifierTool,
    BiasResult,
    LocalBiasDatabase,
    MultiBiasClassifierTool,
)
from src.tools.keyword_extractor import (
    Keyword,
    KeywordExtractor,
    KeywordExtractorTool,
    TopicMatcherTool,
)
from src.tools.rss_aggregator import (
    FeedItem,
    RSSAggregator,
    RSSAggregatorTool,
)
from src.tools.web_search import (
    DuckDuckGoSearch,
    NewsSearchTool,
    SearchResult,
    SearxngSearch,
    WebSearchTool,
)
from src.tools.youtube_research import (
    VideoMetadata,
    YouTubeResearchTool,
    create_youtube_tool,
)

__all__ = [
    # RSS
    "RSSAggregator",
    "RSSAggregatorTool",
    "FeedItem",
    # Web Search
    "DuckDuckGoSearch",
    "SearxngSearch",
    "WebSearchTool",
    "NewsSearchTool",
    "SearchResult",
    # Article Extraction
    "ArticleExtractor",
    "ArticleExtractorTool",
    "MultiArticleExtractorTool",
    "ExtractedArticle",
    # Bias Classification
    "BiasClassifier",
    "BiasClassifierTool",
    "MultiBiasClassifierTool",
    "LocalBiasDatabase",
    "BiasResult",
    "BIAS_LABELS",
    # Keyword Extraction
    "KeywordExtractor",
    "KeywordExtractorTool",
    "TopicMatcherTool",
    "Keyword",
    # YouTube Research
    "YouTubeResearchTool",
    "VideoMetadata",
    "create_youtube_tool",
]
