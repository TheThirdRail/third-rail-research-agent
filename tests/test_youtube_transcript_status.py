"""Tests for YouTube transcript availability reporting."""

from src.tools.youtube_research import VideoMetadata, YouTubeResearchTool


class TestTranscriptStatus:
    """Verify transcript_status field reports availability truthfully."""

    def test_default_status_is_not_requested(self):
        meta = VideoMetadata(
            video_id="abc",
            title="Test",
            description="",
            channel="Chan",
            channel_id="cid",
            upload_date="20260101",
            duration=60,
            view_count=0,
            like_count=0,
            comment_count=0,
        )
        assert meta.transcript_status == "not_requested"

    def test_to_dict_includes_transcript_status(self):
        meta = VideoMetadata(
            video_id="abc",
            title="Test",
            description="",
            channel="Chan",
            channel_id="cid",
            upload_date="20260101",
            duration=60,
            view_count=0,
            like_count=0,
            comment_count=0,
            transcript_status="available_not_downloaded",
        )
        d = meta.to_dict()
        assert d["transcript_status"] == "available_not_downloaded"
        assert "transcript" not in d

    def test_check_availability_returns_available(self):
        tool = YouTubeResearchTool()
        info = {
            "subtitles": {
                "en": [{"ext": "vtt", "url": "http://example.com/sub.vtt"}]
            }
        }
        assert tool._check_transcript_availability(info) == "available_not_downloaded"

    def test_check_availability_returns_missing(self):
        tool = YouTubeResearchTool()
        info = {"subtitles": {}, "automatic_captions": {}}
        assert tool._check_transcript_availability(info) == "missing"

    def test_check_availability_auto_captions(self):
        tool = YouTubeResearchTool()
        info = {
            "subtitles": {},
            "automatic_captions": {
                "en": [{"ext": "json3", "url": "http://example.com/auto.json3"}]
            },
        }
        assert tool._check_transcript_availability(info) == "available_not_downloaded"
