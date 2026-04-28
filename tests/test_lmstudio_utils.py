from src.core.lmstudio_utils import (
    lmstudio_model_endpoints,
    normalize_lmstudio_base_url,
    resolve_lmstudio_api_key,
)


def test_normalize_lmstudio_base_url_adds_v1_when_missing():
    assert (
        normalize_lmstudio_base_url("http://host.docker.internal:1234")
        == "http://host.docker.internal:1234/v1"
    )


def test_normalize_lmstudio_base_url_keeps_single_v1():
    assert (
        normalize_lmstudio_base_url("http://host.docker.internal:1234/v1")
        == "http://host.docker.internal:1234/v1"
    )


def test_lmstudio_model_endpoints_strip_v1_for_deduped_paths():
    assert lmstudio_model_endpoints("http://host.docker.internal:1234/v1") == [
        "http://host.docker.internal:1234/v1/models",
        "http://host.docker.internal:1234/models",
    ]


def test_resolve_lmstudio_api_key_uses_non_empty_fallback():
    assert resolve_lmstudio_api_key("", None) == "lm-studio"
