import csv
import json
from pathlib import Path

FIXTURE_DIR = Path("tests/fixtures/comey_case")


def test_comey_fixture_preserves_missing_right_side_regression_shape():
    rows = list(
        csv.DictReader((FIXTURE_DIR / "source_matrix.csv").open(encoding="utf-8"))
    )
    expectations = json.loads(
        (FIXTURE_DIR / "report_expectations.json").read_text(encoding="utf-8")
    )

    biases = [row["Bias"] for row in rows]

    assert expectations["missing_required_bucket"] == "right_side"
    assert any("-1" in bias for bias in biases)
    assert not any(
        "+1" in bias or "+2" in bias or "+3" in bias or "+4" in bias for bias in biases
    )
    assert any(
        row["Domain"] == expectations["contextual_domain_rejected"] for row in rows
    )
