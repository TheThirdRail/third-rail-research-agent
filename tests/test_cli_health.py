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
        "Install pytesseract/Tesseract or disable screenshot OCR.",
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
        "Install pytesseract/Tesseract or disable screenshot OCR.",
    ) in rows
