"""Channel Profile Loader - Parse channel scope from multiple formats."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ChannelScope:
    """Parsed channel scope data."""

    name: str = ""
    description: str = ""
    worldview: str = ""
    worldview_description: str = ""
    topics: list[str] = field(default_factory=list)
    topic_keywords: dict[str, list[str]] = field(default_factory=dict)
    preferred_sources: dict[str, list[str]] = field(default_factory=dict)
    exclusions: dict[str, list[str]] = field(default_factory=dict)
    content_style: dict[str, Any] = field(default_factory=dict)
    raw_content: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "worldview": self.worldview,
            "worldview_description": self.worldview_description,
            "topics": self.topics,
            "topic_keywords": self.topic_keywords,
            "preferred_sources": self.preferred_sources,
            "exclusions": self.exclusions,
            "content_style": self.content_style,
        }


class ChannelProfileLoader:
    """Load and parse channel profile from various formats."""

    SUPPORTED_EXTENSIONS = {".yaml", ".yml", ".md", ".txt", ".json"}

    def load(self, file_path: str | Path) -> ChannelScope:
        """Load channel profile from file.

        Args:
            file_path: Path to channel profile file

        Returns:
            Parsed ChannelScope object

        Raises:
            ValueError: If file format not supported
            FileNotFoundError: If file doesn't exist
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Channel profile not found: {path}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format: {ext}. Supported: {self.SUPPORTED_EXTENSIONS}"
            )

        content = path.read_text(encoding="utf-8")

        if ext in {".yaml", ".yml"}:
            return self._parse_yaml(content)
        elif ext == ".json":
            return self._parse_json(content)
        elif ext == ".md":
            return self._parse_markdown(content)
        else:
            return self._parse_text(content)

    def load_from_string(self, content: str, format_hint: str = "auto") -> ChannelScope:
        """Load channel profile from string content.

        Args:
            content: Raw content string
            format_hint: Format hint (yaml|json|md|txt|auto)

        Returns:
            Parsed ChannelScope object
        """
        if format_hint == "auto":
            format_hint = self._detect_format(content)

        if format_hint in {"yaml", "yml"}:
            return self._parse_yaml(content)
        elif format_hint == "json":
            return self._parse_json(content)
        elif format_hint == "md":
            return self._parse_markdown(content)
        else:
            return self._parse_text(content)

    def _detect_format(self, content: str) -> str:
        """Auto-detect content format."""
        content_stripped = content.strip()

        # JSON starts with { or [
        if content_stripped.startswith("{") or content_stripped.startswith("["):
            return "json"

        # YAML has key: value patterns
        if ":" in content_stripped.split("\n")[0] and not content_stripped.startswith(
            "#"
        ):
            return "yaml"

        # Markdown has # headers
        if content_stripped.startswith("#"):
            return "md"

        return "txt"

    def _parse_yaml(self, content: str) -> ChannelScope:
        """Parse YAML format."""
        try:
            data = yaml.safe_load(content) or {}
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML: {e}")
            raise ValueError(f"Invalid YAML: {e}") from e

        channel = data.get("channel", data)
        topics_data = data.get("topics", {})

        # Flatten topics
        all_topics = []
        if isinstance(topics_data, dict):
            all_topics = topics_data.get("primary", []) + topics_data.get(
                "secondary", []
            )
        elif isinstance(topics_data, list):
            all_topics = topics_data

        return ChannelScope(
            name=channel.get("name", ""),
            description=channel.get("description", ""),
            worldview=channel.get("worldview", ""),
            worldview_description=channel.get("worldview_description", ""),
            topics=all_topics,
            topic_keywords=data.get("topic_keywords", {}),
            preferred_sources=data.get("preferred_sources", {}),
            exclusions=data.get("exclusions", {}),
            content_style=data.get("content_style", {}),
            raw_content=content,
        )

    def _parse_json(self, content: str) -> ChannelScope:
        """Parse JSON format."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            raise ValueError(f"Invalid JSON: {e}") from e

        return ChannelScope(
            name=data.get("name", ""),
            description=data.get("description", ""),
            worldview=data.get("worldview", ""),
            worldview_description=data.get("worldview_description", ""),
            topics=data.get("topics", []),
            topic_keywords=data.get("topic_keywords", {}),
            preferred_sources=data.get("preferred_sources", {}),
            exclusions=data.get("exclusions", {}),
            content_style=data.get("content_style", {}),
            raw_content=content,
        )

    def _parse_markdown(self, content: str) -> ChannelScope:
        """Parse Markdown format.

        Extracts:
        - Title from # header as name
        - First paragraph as description
        - Sections for worldview, topics, etc.
        """
        lines = content.strip().split("\n")
        scope = ChannelScope(raw_content=content)

        current_section = ""
        current_content: list[str] = []

        for line in lines:
            line_stripped = line.strip()

            # Primary header - channel name
            if line_stripped.startswith("# ") and not scope.name:
                scope.name = line_stripped[2:].strip()
                continue

            # Section headers
            if line_stripped.startswith("## "):
                # Save previous section
                if current_section and current_content:
                    self._save_md_section(scope, current_section, current_content)
                current_section = line_stripped[3:].strip().lower()
                current_content = []
                continue

            # Content lines
            if line_stripped:
                current_content.append(line_stripped)

        # Save last section
        if current_section and current_content:
            self._save_md_section(scope, current_section, current_content)

        # First section without header is description
        if not scope.description and current_content and not current_section:
            scope.description = "\n".join(current_content)

        return scope

    def _save_md_section(
        self, scope: ChannelScope, section: str, content: list[str]
    ) -> None:
        """Save parsed markdown section to scope."""
        text = "\n".join(content)

        if "description" in section or "about" in section:
            scope.description = text
        elif "worldview" in section or "perspective" in section or "bias" in section:
            scope.worldview_description = text
            # Try to extract single-word worldview
            words = text.lower().split()
            for term in [
                "libertarian",
                "conservative",
                "liberal",
                "progressive",
                "centrist",
            ]:
                if term in words:
                    scope.worldview = term
                    break
        elif "topic" in section:
            # Parse bullet points as topics
            scope.topics = [
                line.lstrip("- *•").strip()
                for line in content
                if line.startswith(("-", "*", "•"))
            ]

    def _parse_text(self, content: str) -> ChannelScope:
        """Parse plain text format.

        Treats entire content as description and uses LLM for extraction.
        For now, just stores as raw content.
        """
        lines = content.strip().split("\n")

        # First non-empty line as name if short enough
        name = ""
        description_lines = []

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            if not name and len(line_stripped) < 100:
                name = line_stripped
            else:
                description_lines.append(line_stripped)

        return ChannelScope(
            name=name,
            description="\n".join(description_lines),
            raw_content=content,
        )


# Singleton instance
channel_loader = ChannelProfileLoader()


def load_channel_profile(file_path: str | Path) -> ChannelScope:
    """Convenience function to load channel profile."""
    return channel_loader.load(file_path)
