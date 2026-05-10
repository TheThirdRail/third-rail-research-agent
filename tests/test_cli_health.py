from pathlib import Path

from click.testing import CliRunner

from src.cli import main as cli_main


def test_health_command_reports_readiness(monkeypatch):
    monkeypatch.setattr(
        cli_main,
        "_health_rows",
        lambda: [
            ("Database schema", "ok", "Required tables/columns exist.", ""),
            ("OCR", "warn", "No OCR engine is wired yet.", "Keep OCR disabled."),
        ],
    )

    result = CliRunner().invoke(cli_main.cli, ["health"])

    assert result.exit_code == 0
    assert "Research Agent Health" in result.output
    assert "Database schema" in result.output
    assert "OCR" in result.output
    assert "Health check completed." in result.output


def test_health_command_fails_on_error(monkeypatch):
    monkeypatch.setattr(
        cli_main,
        "_health_rows",
        lambda: [
            (
                "Vector store",
                "error",
                "SEMANTIC_VECTOR_STORE=lancedb but package is not installed.",
                "Install lancedb.",
            )
        ],
    )

    result = CliRunner().invoke(cli_main.cli, ["health"])

    assert result.exit_code != 0
    assert "Health check failed" in result.output
    assert "Vector store" in result.output


def test_health_command_strict_fails_on_warning(monkeypatch):
    monkeypatch.setattr(
        cli_main,
        "_health_rows",
        lambda: [
            (
                "Migrations",
                "warn",
                "No Alembic migration chain is present.",
                "Convert bootstrap schema sync.",
            )
        ],
    )

    result = CliRunner().invoke(cli_main.cli, ["health", "--strict"])

    assert result.exit_code != 0
    assert "Health check has warnings" in result.output


def test_health_rows_launches_chromium_when_screenshot_capture_enabled(monkeypatch):
    monkeypatch.setattr(cli_main.settings, "screenshot_capture_enabled", True)
    monkeypatch.setattr(cli_main, "_package_available", lambda package: True)
    monkeypatch.setattr(
        cli_main,
        "_playwright_chromium_available",
        lambda: (True, "Playwright Chromium launched successfully."),
    )

    rows = cli_main._health_rows()

    assert (
        "Screenshot capture",
        "ok",
        "Playwright Chromium launched successfully.",
        "",
    ) in rows


def test_health_rows_reports_missing_chromium_when_screenshot_capture_enabled(
    monkeypatch,
):
    monkeypatch.setattr(cli_main.settings, "screenshot_capture_enabled", True)
    monkeypatch.setattr(cli_main, "_package_available", lambda package: True)
    monkeypatch.setattr(
        cli_main,
        "_playwright_chromium_available",
        lambda: (False, "Chromium launch failed: executable does not exist"),
    )

    rows = cli_main._health_rows()

    assert (
        "Screenshot capture",
        "error",
        "Chromium launch failed: executable does not exist",
        "Run `playwright install chromium` or disable screenshot capture.",
    ) in rows


def test_health_rows_reports_ocr_disabled(monkeypatch):
    monkeypatch.setattr(cli_main.settings, "screenshot_ocr_enabled", False)

    rows = cli_main._health_rows()

    assert (
        "OCR",
        "ok",
        "Disabled; ocr_text will remain empty.",
        "",
    ) in rows


def test_health_rows_reports_missing_ocr_package_when_enabled(monkeypatch):
    monkeypatch.setattr(cli_main.settings, "screenshot_ocr_enabled", True)
    monkeypatch.setattr(cli_main.settings, "screenshot_ocr_engine", "pytesseract")

    def fake_package_available(package: str) -> bool:
        return package != "pytesseract"

    monkeypatch.setattr(cli_main, "_package_available", fake_package_available)

    rows = cli_main._health_rows()

    assert (
        "OCR",
        "error",
        "SCREENSHOT_OCR_ENABLED=true but pytesseract is unavailable.",
        "Install pytesseract/Tesseract or run `research-agent validate-ocr --force`.",
    ) in rows


def test_health_rows_smoke_tests_ocr_when_enabled(monkeypatch):
    monkeypatch.setattr(cli_main.settings, "screenshot_ocr_enabled", True)
    monkeypatch.setattr(cli_main.settings, "screenshot_ocr_engine", "pytesseract")
    monkeypatch.setattr(cli_main, "_package_available", lambda package: True)
    monkeypatch.setattr(
        cli_main,
        "_pytesseract_ocr_available",
        lambda: (True, "pytesseract OCR smoke test completed."),
    )

    rows = cli_main._health_rows()

    assert (
        "OCR",
        "ok",
        "pytesseract OCR smoke test completed.",
        "",
    ) in rows


def test_health_rows_reports_failed_ocr_smoke_test(monkeypatch):
    monkeypatch.setattr(cli_main.settings, "screenshot_ocr_enabled", True)
    monkeypatch.setattr(cli_main.settings, "screenshot_ocr_engine", "pytesseract")
    monkeypatch.setattr(cli_main, "_package_available", lambda package: True)
    monkeypatch.setattr(
        cli_main,
        "_pytesseract_ocr_available",
        lambda: (False, "OCR smoke test failed: tesseract is not installed"),
    )

    rows = cli_main._health_rows()

    assert (
        "OCR",
        "error",
        "OCR smoke test failed: tesseract is not installed",
        "Install pytesseract/Tesseract or run `research-agent validate-ocr --force`.",
    ) in rows


def test_validate_ocr_fixtures_passes_with_expected_text(monkeypatch, tmp_path):
    fixtures = tmp_path / "ocr"
    fixtures.mkdir()
    (fixtures / "sample.png").write_bytes(b"not-real-image")
    (fixtures / "expectations.json").write_text(
        '{"fixtures":[{"image":"sample.png","expected_text":"Visible OCR 8647","min_score":1.0}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_main, "_ocr_image_text", lambda _path: "Visible OCR 8647")

    report = cli_main.validate_ocr_fixtures(fixtures)

    assert report["status"] == "passed"
    assert report["passed_count"] == 1
    assert report["failed_count"] == 0


def test_validate_ocr_fixtures_fails_on_mismatched_text(monkeypatch, tmp_path):
    fixtures = tmp_path / "ocr"
    fixtures.mkdir()
    (fixtures / "sample.png").write_bytes(b"not-real-image")
    (fixtures / "expectations.json").write_text(
        '{"fixtures":[{"image":"sample.png","expected_text":"Visible OCR 8647","min_score":1.0}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_main, "_ocr_image_text", lambda _path: "wrong story")

    report = cli_main.validate_ocr_fixtures(fixtures)

    assert report["status"] == "failed"
    assert report["failed_count"] == 1


def test_validate_ocr_command_requires_force_when_ocr_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_main, "init_db", lambda: None)
    monkeypatch.setattr(cli_main.settings, "screenshot_ocr_enabled", False)

    result = CliRunner().invoke(
        cli_main.cli,
        ["validate-ocr", "--fixtures", str(tmp_path)],
    )

    assert result.exit_code != 0
    assert "SCREENSHOT_OCR_ENABLED=false" in result.output


def test_validate_ocr_command_outputs_json_when_forced(monkeypatch, tmp_path):
    fixtures = tmp_path / "ocr"
    fixtures.mkdir()
    (fixtures / "sample.png").write_bytes(b"not-real-image")
    (fixtures / "expectations.json").write_text(
        '{"fixtures":[{"image":"sample.png","expected_text":"Visible OCR 8647","min_score":1.0}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_main, "init_db", lambda: None)
    monkeypatch.setattr(cli_main.settings, "screenshot_ocr_enabled", False)
    monkeypatch.setattr(cli_main, "_ocr_image_text", lambda _path: "Visible OCR 8647")

    result = CliRunner().invoke(
        cli_main.cli,
        ["validate-ocr", "--force", "--format", "json", "--fixtures", str(fixtures)],
    )

    assert result.exit_code == 0
    assert '"status": "passed"' in result.output


def test_benchmark_command_runs_live_only_when_requested(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_main, "init_db", lambda: None)
    calls: list[dict] = []

    def fake_run_combined_benchmark(
        fixtures,
        diagnostics_story_ids,
        live_run=False,
        live_limit=None,
    ):
        calls.append(
            {
                "fixtures": fixtures,
                "diagnostics_story_ids": diagnostics_story_ids,
                "live_run": live_run,
                "live_limit": live_limit,
            }
        )
        return {
            "fixtures": {
                "aggregate": {
                    "failed_fixture_count": 0,
                    "fixture_count": 0,
                    "candidate_count": 0,
                    "precision": 0.0,
                    "recall": 0.0,
                    "accuracy": 0.0,
                },
                "results": [],
            },
            "live": {
                "attempted_count": 0,
                "completed_count": 0,
                "failed_count": 0,
                "results": [],
            },
        }

    monkeypatch.setattr(
        "scripts.run_retrieval_benchmark.run_combined_benchmark",
        fake_run_combined_benchmark,
    )

    result = CliRunner().invoke(
        cli_main.cli,
        ["benchmark", "--live", "--live-limit", "1", "--format", "json"],
    )

    assert result.exit_code == 0
    assert calls[0]["live_run"] is True
    assert calls[0]["live_limit"] == 1


def test_benchmark_command_reports_missing_baseline(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_main, "init_db", lambda: None)
    missing = tmp_path / "missing-baseline.json"

    result = CliRunner().invoke(
        cli_main.cli,
        ["benchmark", "--baseline", str(missing)],
    )

    assert result.exit_code != 0
    assert "Benchmark baseline error" in result.output


def test_init_command_runs_migrations_before_schema_sync(monkeypatch):
    calls: list[str] = []

    def fake_run_alembic_upgrade() -> tuple[bool, str]:
        calls.append("migrate")
        return True, "Alembic migrations upgraded to head."

    def fake_init_db() -> None:
        calls.append("init_db")

    monkeypatch.setattr(cli_main, "run_alembic_upgrade", fake_run_alembic_upgrade)
    monkeypatch.setattr(cli_main, "init_db", fake_init_db)
    monkeypatch.setattr(cli_main.settings, "llm_provider", "lmstudio")
    monkeypatch.setattr(Path, "exists", lambda _path: False)

    result = CliRunner().invoke(cli_main.cli, ["init"])

    assert result.exit_code == 0
    assert calls == ["migrate", "init_db"]
    assert "Alembic migrations upgraded to head." in result.output


def test_init_command_falls_back_to_schema_sync_when_migration_unavailable(
    monkeypatch,
):
    calls: list[str] = []

    def fake_run_alembic_upgrade() -> tuple[bool, str]:
        calls.append("migrate")
        return False, "Alembic migration files are not present."

    def fake_init_db() -> None:
        calls.append("init_db")

    monkeypatch.setattr(cli_main, "run_alembic_upgrade", fake_run_alembic_upgrade)
    monkeypatch.setattr(cli_main, "init_db", fake_init_db)
    monkeypatch.setattr(cli_main.settings, "llm_provider", "lmstudio")
    monkeypatch.setattr(Path, "exists", lambda _path: False)

    result = CliRunner().invoke(cli_main.cli, ["init"])

    assert result.exit_code == 0
    assert calls == ["migrate", "init_db"]
    assert "Created missing tables only" in result.output
