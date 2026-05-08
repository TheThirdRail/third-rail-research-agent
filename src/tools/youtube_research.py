"""YouTube Research Tool - Search and extract video metadata using yt-dlp."""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MAX_DESCRIPTION_CHARS = 2000
MAX_TAGS = 20
DEFAULT_SEARCH_RESULTS = 5

TranscriptStatus = Literal["not_requested", "available_not_downloaded", "missing"]


@dataclass
class VideoMetadata:
    """Extracted YouTube video metadata."""

    video_id: str
    title: str
    description: str
    channel: str
    channel_id: str
    upload_date: str
    duration: int
    view_count: int
    like_count: int
    comment_count: int
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    transcript_status: TranscriptStatus = "not_requested"
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "video_id": self.video_id,
            "title": self.title,
            "description": self.description,
            "channel": self.channel,
            "channel_id": self.channel_id,
            "upload_date": self.upload_date,
            "duration": self.duration,
            "view_count": self.view_count,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "tags": self.tags,
            "categories": self.categories,
            "transcript_status": self.transcript_status,
            "url": self.url,
        }


class YouTubeSearchInput(BaseModel):
    """Input for YouTube search."""

    query: str = Field(description="Search query for YouTube")
    max_results: int = Field(
        default=DEFAULT_SEARCH_RESULTS, description="Maximum number of results"
    )


class YouTubeExtractInput(BaseModel):
    """Input for YouTube video extraction."""

    url: str = Field(description="YouTube video URL")
    include_transcript: bool = Field(
        default=True, description="Whether to extract transcript"
    )


class YouTubeResearchTool(BaseTool):
    """Tool for searching YouTube and extracting video metadata.

    Uses yt-dlp for reliable extraction without API keys.
    """

    name: str = "youtube_research"
    description: str = """Search YouTube for videos or extract detailed metadata from a video URL.
    Use 'search' action to find videos matching a query.
    Use 'extract' action to get full metadata including transcript from a video URL."""

    def _run(self, action: str, **kwargs: Any) -> str:
        """Execute YouTube research action.

        Args:
            action: 'search' or 'extract'
            **kwargs: Action-specific parameters
        """
        if action == "search":
            query = kwargs.get("query", "")
            max_results = kwargs.get("max_results", DEFAULT_SEARCH_RESULTS)
            return self._search(query, max_results)
        elif action == "extract":
            url = kwargs.get("url", "")
            include_transcript = kwargs.get("include_transcript", True)
            return self._extract(url, include_transcript)
        else:
            return f"Unknown action: {action}. Use 'search' or 'extract'."

    def _search(self, query: str, max_results: int = DEFAULT_SEARCH_RESULTS) -> str:
        """Search YouTube for videos.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            JSON string with search results
        """
        try:
            import yt_dlp
        except ImportError:
            return "Error: yt-dlp not installed. Run: pip install yt-dlp"

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "default_search": "ytsearch",
        }

        search_query = f"ytsearch{max_results}:{query}"

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(search_query, download=False)

            if not result or "entries" not in result:
                return "No results found"

            videos = []
            for entry in result["entries"]:
                if entry:
                    videos.append(
                        {
                            "video_id": entry.get("id", ""),
                            "title": entry.get("title", ""),
                            "channel": entry.get("channel", entry.get("uploader", "")),
                            "url": entry.get(
                                "url",
                                f"https://youtube.com/watch?v={entry.get('id', '')}",
                            ),
                            "duration": entry.get("duration", 0),
                        }
                    )

            import json

            return json.dumps({"results": videos, "count": len(videos)}, indent=2)

        except Exception as e:
            logger.error(f"YouTube search failed: {e}")
            return f"Search failed: {e}"

    def _extract(self, url: str, include_transcript: bool = True) -> str:
        """Extract metadata from a YouTube video.

        Args:
            url: YouTube video URL
            include_transcript: Whether to extract transcript

        Returns:
            JSON string with video metadata
        """
        try:
            import yt_dlp
        except ImportError:
            return "Error: yt-dlp not installed. Run: pip install yt-dlp"

        # Validate URL
        video_id = self._extract_video_id(url)
        if not video_id:
            return f"Invalid YouTube URL: {url}"

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "writesubtitles": include_transcript,
            "writeautomaticsub": include_transcript,
            "subtitleslangs": ["en"],
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info:
                return "Could not extract video info"

            metadata = VideoMetadata(
                video_id=info.get("id", video_id),
                title=info.get("title", ""),
                description=info.get("description", "")[:MAX_DESCRIPTION_CHARS],
                channel=info.get("channel", info.get("uploader", "")),
                channel_id=info.get("channel_id", ""),
                upload_date=info.get("upload_date", ""),
                duration=info.get("duration", 0),
                view_count=info.get("view_count", 0),
                like_count=info.get("like_count", 0),
                comment_count=info.get("comment_count", 0),
                tags=info.get("tags", [])[:MAX_TAGS],
                categories=info.get("categories", []),
                url=url,
            )

            # Check transcript availability (download not implemented)
            if include_transcript:
                metadata.transcript_status = self._check_transcript_availability(info)

            import json

            return json.dumps(metadata.to_dict(), indent=2)

        except Exception as e:
            logger.error(f"YouTube extraction failed: {e}")
            return f"Extraction failed: {e}"

    def _extract_video_id(self, url: str) -> str | None:
        """Extract video ID from various YouTube URL formats."""
        patterns = [
            r"(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})",
            r"youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _check_transcript_availability(self, info: dict[str, Any]) -> TranscriptStatus:
        """Check whether English captions exist without downloading them.

        Returns one of: ``"available_not_downloaded"``, ``"missing"``, or
        ``"not_requested"``. Full transcript download is not yet implemented.
        """
        subtitles = info.get("subtitles", {})
        auto_captions = info.get("automatic_captions", {})

        for subs in [subtitles, auto_captions]:
            if "en" in subs:
                for sub_format in subs["en"]:
                    if sub_format.get("ext") in ["vtt", "json3", "srv1"]:
                        return "available_not_downloaded"

        return "missing"


# Convenience function
def create_youtube_tool() -> YouTubeResearchTool:
    """Create a YouTube research tool instance."""
    return YouTubeResearchTool()
