import pytest

from src.core.codex_oauth.safety import (
    CodexOAuthConfigError,
    is_local_bridge_url,
    redact_secrets,
    validate_bridge_url,
    validate_prompt_length,
)


def test_bridge_mode_accepts_localhost_urls():
    validate_bridge_url("http://localhost:8787/v1")
    validate_bridge_url("http://127.0.0.1:8787/v1")
    validate_bridge_url("http://[::1]:8787/v1")

    assert is_local_bridge_url("http://127.0.0.1:8787/v1") is True


def test_bridge_mode_accepts_docker_host_gateway():
    validate_bridge_url("http://host.docker.internal:8787/v1")

    assert is_local_bridge_url("http://host.docker.internal:8787/v1") is True


def test_bridge_mode_rejects_placeholder_port():
    with pytest.raises(CodexOAuthConfigError, match="placeholder"):
        validate_bridge_url("http://host.docker.internal:<bridge-port>/v1")


def test_bridge_mode_rejects_non_numeric_port():
    with pytest.raises(CodexOAuthConfigError, match="invalid port"):
        validate_bridge_url("http://localhost:not-a-port/v1")


def test_bridge_mode_rejects_public_urls_by_default():
    with pytest.raises(CodexOAuthConfigError):
        validate_bridge_url("https://example.com/v1")


def test_bridge_mode_rejects_unspecified_bind_address():
    with pytest.raises(CodexOAuthConfigError):
        validate_bridge_url("http://0.0.0.0:8787/v1")


def test_prompt_length_limits_are_enforced():
    validate_prompt_length("hello", 10)

    with pytest.raises(CodexOAuthConfigError):
        validate_prompt_length("too long", 3)


def test_secret_looking_strings_are_redacted():
    message = (
        "Authorization: Bearer mock-testsecret123456 "
        "refresh_token=abc123def456ghi789jwt.token.value "
        "Bearer plainBearerToken1234567890"
    )

    redacted = redact_secrets(message)

    assert "mock-testsecret123456" not in redacted
    assert "abc123def456ghi789jwt.token.value" not in redacted
    assert "plainBearerToken1234567890" not in redacted
    assert "[REDACTED]" in redacted
