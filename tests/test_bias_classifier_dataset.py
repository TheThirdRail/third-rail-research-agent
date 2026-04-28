from src.tools.bias_classifier import BiasClassifier


def test_bias_dataset_includes_source_fields():
    classifier = BiasClassifier()
    result = classifier.classify("reuters.com")

    assert result.method == "dataset"
    assert result.source == "AllSides"
    assert result.source_url is not None


def test_unknown_source_does_not_guess_bias():
    classifier = BiasClassifier()
    result = classifier.classify("unknown-example.com", article_text="Some text")

    assert result.method == "unknown"
    assert result.confidence == 0.0
