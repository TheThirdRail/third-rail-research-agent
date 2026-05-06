from src.tools.article_extractor import ArticleExtractor, ExtractedArticle


def test_selenium_fallback_retries_with_next_user_agent(monkeypatch):
    extractor = ArticleExtractor()

    monkeypatch.setattr(
        "src.tools.article_extractor.settings.enable_selenium_fallback", True
    )
    monkeypatch.setattr("src.tools.article_extractor.settings.max_selenium_attempts", 2)
    monkeypatch.setattr(
        "src.tools.article_extractor.settings.selenium_user_agents",
        "ua-one||ua-two",
    )

    attempts = []

    def fake_extract(url: str, user_agent: str | None):
        attempts.append(user_agent)
        if user_agent == "ua-one":
            return ExtractedArticle(
                title="",
                text="",
                author=None,
                date=None,
                domain="example.com",
                url=url,
                success=False,
                error="Blocked",
                error_code="blocked_challenge",
                extractor_method="selenium",
            )
        return ExtractedArticle(
            title="Recovered",
            text="x" * 300,
            author=None,
            date=None,
            domain="example.com",
            url=url,
            success=True,
            error=None,
            error_code=None,
            extractor_method="selenium",
        )

    monkeypatch.setattr(extractor, "_extract_selenium_sync", fake_extract)

    result = extractor.extract_selenium("https://example.com/story")

    assert result.success is True
    assert attempts == ["ua-one", "ua-two"]


def test_selenium_fallback_disabled(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(
        "src.tools.article_extractor.settings.enable_selenium_fallback", False
    )

    result = extractor.extract_selenium("https://example.com/story")

    assert result.success is False
    assert result.extractor_method == "selenium"
