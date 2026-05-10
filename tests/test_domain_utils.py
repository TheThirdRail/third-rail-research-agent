"""Tests for the shared extract_domain utility."""

from src.utils.url_utils import extract_domain


class TestExtractDomain:
    """Verify extract_domain handles URLs, bare domains, and edge cases."""

    def test_full_https_url(self):
        assert extract_domain("https://example.com/path") == "example.com"

    def test_full_http_url(self):
        assert extract_domain("http://example.com/path?q=1") == "example.com"

    def test_strips_www_prefix(self):
        assert extract_domain("https://www.example.com/page") == "example.com"

    def test_preserves_subdomain(self):
        assert extract_domain("https://news.example.com/article") == "news.example.com"

    def test_bare_domain(self):
        assert extract_domain("example.com") == "example.com"

    def test_bare_domain_with_www(self):
        assert extract_domain("www.example.com") == "example.com"

    def test_empty_string(self):
        assert extract_domain("") == ""

    def test_whitespace_only(self):
        assert extract_domain("   ") == ""

    def test_lowercases_output(self):
        assert extract_domain("https://WWW.EXAMPLE.COM/Path") == "example.com"

    def test_bare_domain_lowercased(self):
        assert extract_domain("CNN.com") == "cnn.com"

    def test_protocol_relative_url(self):
        assert extract_domain("//cdn.example.com/file") == "cdn.example.com"

    def test_url_with_port(self):
        assert extract_domain("https://localhost:8080/api") == "localhost:8080"

    def test_invalid_url_returns_cleaned_input(self):
        result = extract_domain("not-a-url")
        assert result == "not-a-url"
