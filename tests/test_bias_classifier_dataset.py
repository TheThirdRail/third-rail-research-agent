from src.tools.bias_classifier import BiasClassifier


def test_bias_dataset_includes_source_fields():
    classifier = BiasClassifier()
    result = classifier.classify("reuters.com")

    assert result.method == "dataset"
    assert result.source == "source_registry"
    assert result.source_url is not None


def test_unknown_source_uses_text_fallback():
    classifier = BiasClassifier()
    result = classifier.classify("unknown-example.com", article_text="Some text")

    assert result.method in {"heuristic", "llm"}
    assert result.confidence > 0.0
