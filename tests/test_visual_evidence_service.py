from src.schemas.visual_evidence import MediaPointer
from src.services.visual_evidence_service import VisualEvidenceService
from src.tools.article_extractor import ArticleExtractor


def test_article_extractor_captures_media_metadata():
    html = """
    <html>
      <head><meta property="og:image" content="https://example.com/card.jpg"></head>
      <body>
        <a href="https://x.com/example/status/123">post</a>
        <figure>
          <img src="https://example.com/inline.jpg" alt="Shells arranged as 8647">
          <figcaption>Photo shows seashells spelling 8647.</figcaption>
        </figure>
        <p>Body text about the story.</p>
      </body>
    </html>
    """
    article = ArticleExtractor()._extract_from_html(
        url="https://example.com/story",
        html_content=html,
        method="test",
    )

    assert article.og_image_url == "https://example.com/card.jpg"
    assert "https://x.com/example/status/123" in article.embedded_post_urls
    assert "Shells arranged as 8647" in article.image_alt_text
    assert "Photo shows seashells spelling 8647." in article.media_captions


def test_visual_evidence_uses_router_output(monkeypatch):
    class FakeRouter:
        def complete(self, messages, temperature=None, max_tokens=None):
            return """
            {
              "observable_text": "8647",
              "visible_symbols_or_numbers": ["8647"],
              "observable_objects": ["seashells"],
              "platform": "x",
              "confidence": 0.91
            }
            """

    monkeypatch.setattr(
        "src.services.visual_evidence_service.get_llm_router",
        lambda agent_name=None: FakeRouter(),
    )

    bundle = VisualEvidenceService().analyze(
        [
            MediaPointer(
                source_url="https://example.com/story",
                media_url="https://example.com/card.jpg",
                alt_text="Shells arranged as 8647",
            )
        ]
    )

    assert bundle.records[0].observable_text == "8647"
    assert bundle.records[0].visible_symbols_or_numbers == ["8647"]
    assert bundle.records[0].interpretation == ""
    assert bundle.records[0].legal_characterization == ""


def test_visual_evidence_falls_back_to_metadata_on_model_failure(monkeypatch):
    class FailingRouter:
        def complete(self, messages, temperature=None, max_tokens=None):
            raise RuntimeError("no vision model")

    monkeypatch.setattr(
        "src.services.visual_evidence_service.get_llm_router",
        lambda agent_name=None: FailingRouter(),
    )

    bundle = VisualEvidenceService().analyze(
        [
            MediaPointer(
                source_url="https://example.com/story",
                media_url="https://example.com/card.jpg",
                alt_text="Shells arranged as 8647",
            )
        ]
    )

    assert bundle.limitations
    assert bundle.records[0].observable_text == "Shells arranged as 8647"
    assert bundle.records[0].visible_symbols_or_numbers == ["8647"]
