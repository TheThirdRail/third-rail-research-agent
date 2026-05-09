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
    "Keyword",
]
