import logging

import pytest

from src.tools.channel_profile_loader import ChannelProfileLoader


def test_invalid_yaml_logs_profile_parse_warning(caplog):
    loader = ChannelProfileLoader()
    caplog.set_level(logging.WARNING)

    with pytest.raises(ValueError):
        loader.load_from_string("channel: [broken", "yaml")

    assert "Failed to parse channel profile YAML" in caplog.text


def test_auto_plain_text_fallback_logs_warning(caplog):
    loader = ChannelProfileLoader()
    caplog.set_level(logging.WARNING)

    scope = loader.load_from_string("My Channel\nPlain text profile.", "auto")

    assert scope.name == "My Channel"
    assert "plain-text parser fallback" in caplog.text
