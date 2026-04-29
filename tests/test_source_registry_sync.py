from pathlib import Path

import yaml

from scripts.sync_source_configs import validate_configs


def write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_source_registry_sync_check_accepts_matching_derivatives(tmp_path):
    write_yaml(
        tmp_path / "source_registry.yaml",
        {
            "sources": [
                {
                    "name": "Example",
                    "domain": "example.com",
                    "bias": 1,
                    "rss_urls": ["https://example.com/rss"],
                }
            ]
        },
    )
    write_yaml(
        tmp_path / "bias_sources.yaml",
        {"sources": {"example.com": {"bias": 1}}},
    )
    write_yaml(
        tmp_path / "rss_feeds.yaml",
        {
            "feeds": {
                "slight_right": [{"name": "Example", "url": "https://example.com/rss"}]
            }
        },
    )

    assert validate_configs(tmp_path) == []


def test_source_registry_sync_check_rejects_bias_drift(tmp_path):
    write_yaml(
        tmp_path / "source_registry.yaml",
        {"sources": [{"name": "Example", "domain": "example.com", "bias": 1}]},
    )
    write_yaml(
        tmp_path / "bias_sources.yaml",
        {"sources": {"example.com": {"bias": -1}}},
    )
    write_yaml(tmp_path / "rss_feeds.yaml", {"feeds": {}})

    errors = validate_configs(tmp_path)

    assert any("bias differs" in error for error in errors)
