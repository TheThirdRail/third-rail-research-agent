"""Channel profile API routes."""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.core.config import settings
from src.tools.channel_profile_loader import channel_loader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channel", tags=["channel"])


class ChannelProfileResponse(BaseModel):
    """Response model for channel profile."""

    name: str
    description: str
    worldview: str
    worldview_description: str
    topics: list[str]
    topic_keywords: dict[str, list[str]]
    preferred_sources: dict[str, list[str]]
    content_style: dict[str, Any]


class ChannelUploadResponse(BaseModel):
    """Response for channel profile upload."""

    success: bool
    message: str
    profile: ChannelProfileResponse | None = None


@router.get("/profile", response_model=ChannelProfileResponse)
async def get_channel_profile() -> ChannelProfileResponse:
    """Get the current active channel profile."""
    try:
        scope = channel_loader.load(settings.channel_profile_path)
        return ChannelProfileResponse(
            name=scope.name,
            description=scope.description,
            worldview=scope.worldview,
            worldview_description=scope.worldview_description,
            topics=scope.topics,
            topic_keywords=scope.topic_keywords,
            preferred_sources=scope.preferred_sources,
            content_style=scope.content_style,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail="Channel profile not found"
        ) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/upload", response_model=ChannelUploadResponse)
async def upload_channel_profile(file: UploadFile = File(...)) -> ChannelUploadResponse:
    """Upload and parse a channel scope document.

    Supports:
    - YAML (.yaml, .yml)
    - JSON (.json)
    - Markdown (.md)
    - Plain text (.txt)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Check extension
    ext = Path(file.filename).suffix.lower()
    if ext not in channel_loader.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {ext}. Supported: {list(channel_loader.SUPPORTED_EXTENSIONS)}",
        )

    try:
        # Read file content
        content = await file.read()
        content_str = content.decode("utf-8")

        # Parse based on format
        format_hint = ext.lstrip(".")
        if format_hint in {"yaml", "yml"}:
            format_hint = "yaml"

        scope = channel_loader.load_from_string(content_str, format_hint)

        # Save to config directory
        output_path = settings.config_dir / "channel_profile.yaml"

        # Convert to YAML and save
        import yaml

        yaml_content = yaml.safe_dump(
            scope.to_dict(), default_flow_style=False, allow_unicode=True
        )
        output_path.write_text(yaml_content, encoding="utf-8")

        logger.info(f"Channel profile uploaded: {scope.name}")

        return ChannelUploadResponse(
            success=True,
            message=f"Channel profile '{scope.name}' uploaded successfully",
            profile=ChannelProfileResponse(
                name=scope.name,
                description=scope.description,
                worldview=scope.worldview,
                worldview_description=scope.worldview_description,
                topics=scope.topics,
                topic_keywords=scope.topic_keywords,
                preferred_sources=scope.preferred_sources,
                content_style=scope.content_style,
            ),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid file content: {e}") from e
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="File must be UTF-8 encoded text"
        ) from None
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}") from e
