"""CLI entry point for Research Agent."""

import importlib.util
import json
import re
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.core.config import settings
from src.database import get_alembic_revision_status, init_db, run_alembic_upgrade

console = Console()

DEFAULT_OCR_FIXTURE_DIR = Path("tests/fixtures/ocr")


def load_channel_topics() -> list[str]:
    """Load topics from channel profile."""
    try:
        with open(settings.channel_profile_path) as f:
            profile = yaml.safe_load(f)

        topics = []
        for _category, keywords in profile.get("topic_keywords", {}).items():
            topics.extend(keywords[:3])  # First 3 from each category

        return topics[:20]  # Max 20 topics
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load channel profile: {e}[/yellow]")
        return ["politics", "geopolitics", "news"]


def _package_available(package_name: str) -> bool:
    """Return whether an optional package can be imported."""
    return importlib.util.find_spec(package_name) is not None


def _playwright_chromium_available() -> tuple[bool, str]:
    """Return whether Playwright can launch Chromium."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return False, f"Playwright import failed: {exc}"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--no-sandbox"])
            browser.close()
    except Exception as exc:
        return False, f"Chromium launch failed: {exc}"

    return True, "Playwright Chromium launched successfully."


def _pytesseract_ocr_available() -> tuple[bool, str]:
    """Return whether pytesseract can execute OCR through the system binary."""
    import tempfile

    try:
        import pytesseract  # type: ignore[import-not-found]
        from PIL import Image, ImageDraw
    except Exception as exc:
        return False, f"OCR import failed: {exc}"

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "ocr-smoke.png"
            image = Image.new("RGB", (140, 48), "white")
            draw = ImageDraw.Draw(image)
            draw.text((12, 12), "OK", fill="black")
            image.save(image_path)
            pytesseract.image_to_string(str(image_path))
    except Exception as exc:
        return False, f"OCR smoke test failed: {exc}"

    return True, "pytesseract OCR smoke test completed."


def _ocr_image_text(image_path: Path) -> str:
    """Extract OCR text from an image using the configured OCR engine."""
    if settings.screenshot_ocr_engine != "pytesseract":
        raise RuntimeError(f"Unsupported OCR engine: {settings.screenshot_ocr_engine}")
    try:
        import pytesseract  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError(f"pytesseract is unavailable: {exc}") from exc
    try:
        return str(pytesseract.image_to_string(str(image_path))).strip()
    except Exception as exc:
        raise RuntimeError(f"OCR failed for {image_path}: {exc}") from exc


def _normalize_ocr_text(value: str) -> list[str]:
    """Normalize OCR text into comparable tokens."""
    return re.findall(r"[a-z0-9]+", value.lower())


def _score_ocr_match(expected: str, actual: str) -> float:
    """Return the share of expected tokens present in actual OCR output."""
    expected_tokens = _normalize_ocr_text(expected)
    if not expected_tokens:
        return 0.0
    actual_tokens = set(_normalize_ocr_text(actual))
    matched = sum(1 for token in expected_tokens if token in actual_tokens)
    return round(matched / len(expected_tokens), 6)


def validate_ocr_fixtures(fixtures_dir: Path) -> dict[str, object]:
    """Run OCR over fixture images and return a serializable validation report."""
    expectations_path = fixtures_dir / "expectations.json"
    if not expectations_path.exists():
        return {
            "status": "failed",
            "fixture_dir": str(fixtures_dir),
            "passed_count": 0,
            "failed_count": 1,
            "results": [
                {
                    "image": "",
                    "status": "failed",
                    "expected_text": "",
                    "actual_text": "",
                    "score": 0.0,
                    "error": f"Missing OCR expectations file: {expectations_path}",
                }
            ],
        }

    data = json.loads(expectations_path.read_text(encoding="utf-8"))
    fixtures = data.get("fixtures", [])
    results = []
    for fixture in fixtures:
        image_name = str(fixture.get("image", ""))
        expected_text = str(fixture.get("expected_text", ""))
        min_score = float(fixture.get("min_score", 1.0))
        image_path = fixtures_dir / image_name
        if not image_name or not image_path.exists():
            results.append(
                {
                    "image": image_name,
                    "status": "failed",
                    "expected_text": expected_text,
                    "actual_text": "",
                    "score": 0.0,
                    "error": f"Missing OCR fixture image: {image_path}",
                }
            )
            continue
        try:
            actual_text = _ocr_image_text(image_path)
            score = _score_ocr_match(expected_text, actual_text)
            passed = score >= min_score
            results.append(
                {
                    "image": image_name,
                    "status": "passed" if passed else "failed",
                    "expected_text": expected_text,
                    "actual_text": actual_text,
                    "score": score,
                    "min_score": min_score,
                    "error": "" if passed else "OCR text did not match expectation.",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "image": image_name,
                    "status": "failed",
                    "expected_text": expected_text,
                    "actual_text": "",
                    "score": 0.0,
                    "min_score": min_score,
                    "error": str(exc),
                }
            )

    passed_count = sum(1 for result in results if result["status"] == "passed")
    failed_count = len(results) - passed_count
    return {
        "status": "passed" if failed_count == 0 and results else "failed",
        "fixture_dir": str(fixtures_dir),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "results": results,
    }


def _format_ocr_validation_markdown(report: dict[str, object]) -> str:
    """Format OCR validation results for console output."""
    lines = [
        "# OCR Validation Report",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Status | {report['status']} |",
        f"| Passed | {report['passed_count']} |",
        f"| Failed | {report['failed_count']} |",
        "",
        "| Image | Status | Score | Expected | Actual/Error |",
        "|---|---|---:|---|---|",
    ]
    for result in report["results"]:  # type: ignore[index]
        actual_or_error = result.get("actual_text") or result.get("error")  # type: ignore[union-attr]
        lines.append(
            "| {image} | {status} | {score:.3f} | {expected_text} | {actual} |".format(
                image=result.get("image", ""),  # type: ignore[union-attr]
                status=result.get("status", ""),  # type: ignore[union-attr]
                score=float(result.get("score", 0.0)),  # type: ignore[union-attr]
                expected_text=result.get("expected_text", ""),  # type: ignore[union-attr]
                actual=actual_or_error,
            )
        )
    return "\n".join(lines) + "\n"


def _provider_key_configured(provider: str) -> bool:
    """Check provider configuration without returning secret values."""
    key_check = {
        "openrouter": bool(settings.openrouter_api_key),
        "gemini": bool(settings.google_api_key or settings.gemini_api_key),
        "anthropic": bool(settings.anthropic_api_key),
        "groq": bool(settings.groq_api_key),
        "openai": bool(settings.openai_api_key),
        "lmstudio": True,
        "ollama": True,
        "grok": bool(settings.xai_api_key),
        "cerebras": bool(settings.cerebras_api_key),
        "sambanova": bool(settings.sambanova_api_key),
        "mistral": bool(settings.mistral_api_key),
    }
    return bool(key_check.get(provider.strip().lower(), False))


def _health_rows() -> list[tuple[str, str, str, str]]:
    """Build readiness rows as (component, status, detail, action)."""
    from sqlalchemy import inspect

    from src.database.models import Base
    from src.database.session import HARDENING_COLUMNS, engine

    rows: list[tuple[str, str, str, str]] = []

    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        expected_tables = set(Base.metadata.tables)
        missing_tables = sorted(expected_tables - tables)
        missing_columns: list[str] = []
        for table, column, _sql_type, _default in HARDENING_COLUMNS:
            if table not in tables:
                continue
            columns = {col["name"] for col in inspector.get_columns(table)}
            if column not in columns:
                missing_columns.append(f"{table}.{column}")
        if missing_tables or missing_columns:
            detail = ", ".join((missing_tables + missing_columns)[:6])
            rows.append(
                (
                    "Database schema",
                    "error",
                    f"Missing schema objects: {detail}",
                    "Run `research-agent init`.",
                )
            )
        else:
            rows.append(("Database schema", "ok", "Required tables/columns exist.", ""))
    except Exception as exc:
        rows.append(
            (
                "Database schema",
                "error",
                f"Could not inspect database: {exc}",
                "Check DATABASE_URL and run `research-agent init`.",
            )
        )

    provider = settings.llm_provider.strip().lower()
    if _provider_key_configured(provider):
        rows.append(("LLM provider", "ok", f"{provider} is configured.", ""))
    else:
        rows.append(
            (
                "LLM provider",
                "warn",
                f"{provider} is selected but its API key is not configured.",
                "Set the provider API key or choose a local provider.",
            )
        )

    if settings.embedding_provider == "fake":
        status = (
            "warn"
            if (
                settings.semantic_memory_enabled
                or settings.semantic_candidate_scoring_enabled
            )
            else "ok"
        )
        rows.append(
            (
                "Embeddings",
                status,
                "Using deterministic fake embeddings.",
                "Set EMBEDDING_PROVIDER=lmstudio for production semantic quality.",
            )
        )
    elif settings.embedding_provider in {"lmstudio", "lm_studio", "lm-studio"}:
        if settings.embedding_model and settings.embedding_model != "fake-hash-v1":
            rows.append(
                (
                    "Embeddings",
                    "ok",
                    f"LM Studio embeddings configured for {settings.embedding_model}.",
                    "",
                )
            )
        else:
            rows.append(
                (
                    "Embeddings",
                    "error",
                    "LM Studio embeddings selected without a real model.",
                    "Set EMBEDDING_MODEL.",
                )
            )
    else:
        rows.append(
            (
                "Embeddings",
                "error",
                f"Unsupported embedding provider: {settings.embedding_provider}",
                "Use `fake` or `lmstudio`.",
            )
        )

    vector_store = settings.semantic_vector_store.strip().lower()
    if vector_store in {"", "none", "disabled", "sql"}:
        rows.append(("Vector store", "ok", "SQL-only semantic retrieval selected.", ""))
    elif vector_store == "lancedb":
        if _package_available("lancedb"):
            rows.append(
                (
                    "Vector store",
                    "ok",
                    "LanceDB package is available.",
                    "",
                )
            )
        else:
            status = "warn" if settings.semantic_fail_open else "error"
            rows.append(
                (
                    "Vector store",
                    status,
                    "SEMANTIC_VECTOR_STORE=lancedb but package is not installed.",
                    "Install `lancedb` or use SEMANTIC_VECTOR_STORE=none.",
                )
            )
    else:
        rows.append(
            (
                "Vector store",
                "error",
                f"Unsupported vector store: {settings.semantic_vector_store}",
                "Use `none` or `lancedb`.",
            )
        )

    if settings.screenshot_capture_enabled:
        if _package_available("playwright"):
            chromium_available, chromium_detail = _playwright_chromium_available()
            if chromium_available:
                rows.append(
                    (
                        "Screenshot capture",
                        "ok",
                        chromium_detail,
                        "",
                    )
                )
            else:
                rows.append(
                    (
                        "Screenshot capture",
                        "error",
                        chromium_detail,
                        "Run `playwright install chromium` or disable screenshot capture.",
                    )
                )
        else:
            rows.append(
                (
                    "Screenshot capture",
                    "error",
                    "Screenshot capture enabled but Playwright is unavailable.",
                    "Install Playwright or disable screenshot capture.",
                )
            )
    else:
        rows.append(
            (
                "Screenshot capture",
                "ok",
                "Disabled by default; structured fallbacks will be used.",
                "",
            )
        )

    if settings.screenshot_ocr_enabled:
        if settings.screenshot_ocr_engine != "pytesseract":
            rows.append(
                (
                    "OCR",
                    "error",
                    f"Unsupported OCR engine: {settings.screenshot_ocr_engine}",
                    "Use SCREENSHOT_OCR_ENGINE=pytesseract or disable OCR.",
                )
            )
        elif _package_available("pytesseract"):
            ocr_available, ocr_detail = _pytesseract_ocr_available()
            if ocr_available:
                rows.append(
                    (
                        "OCR",
                        "ok",
                        ocr_detail,
                        "",
                    )
                )
            else:
                rows.append(
                    (
                        "OCR",
                        "error",
                        ocr_detail,
                        "Install pytesseract/Tesseract or run `research-agent validate-ocr --force`.",
                    )
                )
        else:
            rows.append(
                (
                    "OCR",
                    "error",
                    "SCREENSHOT_OCR_ENABLED=true but pytesseract is unavailable.",
                    "Install pytesseract/Tesseract or run `research-agent validate-ocr --force`.",
                )
            )
    else:
        rows.append(
            (
                "OCR",
                "ok",
                "Disabled; ocr_text will remain empty.",
                "",
            )
        )

    migration_status, migration_detail = get_alembic_revision_status()
    migration_action = "" if migration_status == "ok" else "Run `research-agent init`."
    rows.append(("Migrations", migration_status, migration_detail, migration_action))

    for warning in settings.validate_feature_dependencies():
        rows.append(("Feature config", "warn", warning, "Review .env settings."))

    return rows


@click.group()
@click.version_option(version="0.1.0", prog_name="research-agent")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Research Agent - AI-powered news research for YouTube creators.

    Find relevant stories, analyze political bias across sources,
    separate facts from opinions, and generate content outlines.
    """
    # Initialize database on startup. The explicit init command runs migrations first.
    if ctx.invoked_subcommand != "init":
        init_db()


@cli.command()
@click.option("--count", "-n", default=10, help="Number of stories to discover")
@click.option("--topics", "-t", multiple=True, help="Topic keywords to search")
def discover(count: int, topics: tuple[str, ...]) -> None:
    """Discover relevant stories for your channel.

    Searches RSS feeds and web for stories matching your channel's focus areas.
    """
    from src.services import DiscoveryService

    # Get topics from args or channel profile
    topic_list = list(topics) if topics else None

    console.print(
        Panel(
            f"[bold]Discovering stories for topics:[/bold]\n{', '.join(topic_list[:10]) if topic_list else 'Channel profile'}"
        )
    )

    with console.status("[bold green]Searching for stories..."):
        try:
            service = DiscoveryService()
            result = service.discover(topic_list, count=count)
            console.print("\n[bold green]Discovery Complete![/bold green]\n")
            console.print(result.get("raw_output", "No results"))
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise click.Abort() from None


@cli.command()
@click.option("--url", "-u", default=None, help="URL of story to analyze")
@click.option("--describe", "-d", default=None, help="Description of story to research")
@click.option("--output", "-o", default=None, help="Output file for report (markdown)")
@click.option(
    "--strict/--no-strict", default=None, help="Override strict bucket enforcement."
)
@click.option(
    "--semantic-memory/--no-semantic-memory",
    default=None,
    help="Enable/disable semantic memory.",
)
@click.option(
    "--semantic-scoring/--no-semantic-scoring",
    default=None,
    help="Enable/disable semantic candidate scoring.",
)
@click.option(
    "--visual-evidence/--no-visual-evidence",
    default=None,
    help="Enable/disable visual evidence resolution.",
)
@click.option(
    "--screenshot/--no-screenshot",
    default=None,
    help="Enable/disable screenshot capture.",
)
@click.option(
    "--embedding-provider",
    default=None,
    help="Embedding provider (e.g., lmstudio, fake).",
)
@click.option("--embedding-model", default=None, help="Embedding model name.")
@click.option(
    "--vector-store", default=None, help="Vector store backend (e.g., lancedb, none)."
)
def analyze(
    url: str | None,
    describe: str | None,
    output: str | None,
    strict: bool | None,
    semantic_memory: bool | None,
    semantic_scoring: bool | None,
    visual_evidence: bool | None,
    screenshot: bool | None,
    embedding_provider: str | None,
    embedding_model: str | None,
    vector_store: str | None,
) -> None:
    """Analyze a specific story from URL or description.

    Aggregates sources from across the political spectrum,
    classifies bias, separates facts from opinions, and generates a report.
    """
    from src.schemas.analysis_options import AnalysisOptions
    from src.services import AnalysisService

    if not url and not describe:
        console.print("[bold red]Error:[/bold red] Please provide --url or --describe")
        raise click.Abort()

    story_desc = describe or f"Story from URL: {url}"

    # Build per-run options from CLI flags (None values are excluded)
    option_kwargs: dict[str, object] = {}
    if strict is not None:
        option_kwargs["strict_bucket_enforcement"] = strict
    if semantic_memory is not None:
        option_kwargs["enable_semantic_memory"] = semantic_memory
    if semantic_scoring is not None:
        option_kwargs["enable_semantic_candidate_scoring"] = semantic_scoring
    if visual_evidence is not None:
        option_kwargs["enable_visual_evidence_resolution"] = visual_evidence
    if screenshot is not None:
        option_kwargs["enable_screenshot_capture"] = screenshot
    if embedding_provider is not None:
        option_kwargs["embedding_provider"] = embedding_provider
    if embedding_model is not None:
        option_kwargs["embedding_model"] = embedding_model
    if vector_store is not None:
        option_kwargs["vector_store"] = vector_store
    options = AnalysisOptions(**option_kwargs) if option_kwargs else None

    console.print(Panel(f"[bold]Analyzing story:[/bold]\n{story_desc[:200]}"))
    if options:
        console.print(
            f"[dim]Per-run options: {options.model_dump(exclude_none=True)}[/dim]"
        )

    with console.status("[bold green]Running multi-source analysis..."):
        try:
            service = AnalysisService()
            result = service.analyze(story_desc, url, options=options)
            report = result.get("report", "No report generated")

            console.print("\n[bold green]Analysis Complete![/bold green]\n")
            console.print(f"[dim]Story ID: {result.get('story_id', 'N/A')[:8]}[/dim]\n")
            console.print(report)

            # Save to file if requested
            if output:
                Path(output).write_text(report, encoding="utf-8")
                console.print(f"\n[dim]Report saved to: {output}[/dim]")

        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise click.Abort() from None


@cli.group()
def report() -> None:
    """View and manage analysis reports."""
    pass


@report.command(name="list")
@click.option("--limit", "-l", default=10, help="Number of reports to show")
def list_reports(limit: int) -> None:
    """List recent analysis reports from the database."""
    from src.database import StoryCRUD, get_session

    session = get_session()
    crud = StoryCRUD(session)
    stories = crud.list_recent(limit, status="analyzed")

    if not stories:
        console.print("[yellow]No analyzed stories found.[/yellow]")
        return

    table = Table(title="Recent Analyses")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Title", style="white", max_width=50)
    table.add_column("Date", style="cyan")
    table.add_column("Status", style="green")

    for story in stories:
        table.add_row(
            story.id[:8],
            story.title[:50],
            story.discovered_at.strftime("%Y-%m-%d"),
            story.status,
        )

    console.print(table)
    session.close()


@cli.group()
def performance() -> None:
    """Track YouTube video performance."""
    pass


@performance.command(name="add")
@click.option("--story-id", required=True, help="Story ID to attach performance to")
@click.option("--views", required=True, type=int, help="Total view count")
@click.option("--likes", type=int, default=0, help="Like count")
@click.option("--comments", type=int, default=0, help="Comment count")
@click.option("--video-id", default=None, help="YouTube video ID")
def add_performance(
    story_id: str,
    views: int,
    likes: int,
    comments: int,
    video_id: str | None,
) -> None:
    """Add YouTube performance data to a story."""
    from src.database import PerformanceCRUD, StoryCRUD, get_session

    session = get_session()

    # Verify story exists
    story_crud = StoryCRUD(session)
    story = story_crud.get_by_id(story_id)

    if not story:
        console.print(f"[bold red]Error:[/bold red] Story {story_id} not found")
        session.close()
        raise click.Abort()

    # Add performance data
    perf_crud = PerformanceCRUD(session)
    perf_crud.create(
        story_id=story_id,
        youtube_video_id=video_id,
        views_total=views,
        likes=likes,
        comments=comments,
    )

    console.print(
        f"[bold green]Performance added for story:[/bold green] {story.title[:50]}"
    )
    console.print(f"  Views: {views:,} | Likes: {likes:,} | Comments: {comments:,}")

    session.close()


@cli.group()
def profile() -> None:
    """Manage channel profile and scope."""
    pass


@profile.command(name="upload")
@click.option(
    "--file",
    "-f",
    required=True,
    type=click.Path(exists=True),
    help="Path to channel scope document",
)
def profile_upload(file: str) -> None:
    """Upload a channel scope document.

    Supports: YAML, JSON, Markdown, or plain text.
    """
    from src.tools.channel_profile_loader import channel_loader

    try:
        scope = channel_loader.load(file)

        # Save to config directory
        import yaml as _yaml

        output_path = settings.config_dir / "channel_profile.yaml"
        yaml_content = _yaml.safe_dump(
            scope.to_dict(), default_flow_style=False, allow_unicode=True
        )
        output_path.write_text(yaml_content, encoding="utf-8")

        console.print(
            Panel(
                f"[bold green]✓ Channel profile uploaded[/bold green]\n\nName: {scope.name}\nWorldview: {scope.worldview}\nTopics: {len(scope.topics)}"
            )
        )
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise click.Abort() from None


@profile.command(name="show")
def profile_show() -> None:
    """Show current channel profile."""
    from src.tools.channel_profile_loader import channel_loader

    try:
        scope = channel_loader.load(settings.channel_profile_path)

        table = Table(title=f"Channel Profile: {scope.name}")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Name", scope.name)
        table.add_row("Worldview", scope.worldview)
        table.add_row(
            "Description",
            scope.description[:200] + "..."
            if len(scope.description) > 200
            else scope.description,
        )
        table.add_row("Topics", ", ".join(scope.topics[:10]))

        console.print(table)
    except FileNotFoundError:
        console.print(
            "[yellow]No channel profile found. Use 'profile upload' to add one.[/yellow]"
        )
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


@cli.group(name="codex-oauth")
def codex_oauth() -> None:
    """Diagnose optional local Codex OAuth testing."""
    pass


@codex_oauth.command(name="status")
def codex_oauth_status() -> None:
    """Show Codex OAuth testing status without exposing credentials."""
    from src.core.codex_oauth import cli_adapter
    from src.core.codex_oauth.bridge import diagnose_bridge

    bridge = diagnose_bridge(settings)
    cli_path = cli_adapter.find_codex(settings.codex_cli_command)

    table = Table(title="Codex OAuth Testing Status")
    table.add_column("Check", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Enabled", str(settings.codex_oauth_testing_enabled))
    table.add_row("Mode", settings.codex_oauth_mode)
    table.add_row(
        "OPENAI_BASE_URL configured",
        str(bridge["openai_base_url_configured"]),
    )
    table.add_row("Bridge URL local", str(bridge["openai_base_url_local"]))
    table.add_row("Codex CLI exists", str(bool(cli_path)))
    table.add_row("Public API blocked", str(not settings.codex_allow_public_api))
    console.print(table)


@codex_oauth.command(name="diagnose")
def codex_oauth_diagnose() -> None:
    """Run Codex OAuth testing diagnostics."""
    from src.core.codex_oauth import cli_adapter
    from src.core.codex_oauth.bridge import diagnose_bridge
    from src.core.codex_oauth.safety import redact_secrets

    errors: list[str] = []
    warnings: list[str] = []

    if not settings.codex_oauth_testing_enabled:
        console.print("[yellow]Codex OAuth testing is disabled.[/yellow]")
        return

    if settings.codex_allow_public_api:
        warnings.append("CODEX_ALLOW_PUBLIC_API=true; do not expose this publicly.")
    if not settings.codex_require_localhost:
        warnings.append("CODEX_REQUIRE_LOCALHOST=false; localhost enforcement is off.")

    if settings.codex_oauth_mode == "openai_compatible_bridge":
        bridge = diagnose_bridge(settings)
        errors.extend(bridge["errors"])
        warnings.extend(bridge["warnings"])
    elif settings.codex_oauth_mode == "codex_cli":
        status = cli_adapter.status(settings)
        if not status.exists:
            errors.append(status.message)
        elif not status.login_ok:
            errors.append(
                "Codex CLI is available but login status failed. Run `codex login`."
            )
            if status.message:
                warnings.append(status.message)
    else:
        errors.append(
            "CODEX_OAUTH_MODE must be disabled, openai_compatible_bridge, or codex_cli."
        )

    if errors:
        console.print("[bold red]Codex OAuth diagnostics failed:[/bold red]")
        for error in errors:
            console.print(f"  - {redact_secrets(error)}")
    else:
        console.print("[bold green]Codex OAuth diagnostics passed.[/bold green]")

    if warnings:
        console.print("[yellow]Warnings:[/yellow]")
        for warning in warnings:
            console.print(f"  - {redact_secrets(warning)}")

    if errors:
        raise click.Abort() from None


@codex_oauth.command(name="test")
@click.argument("prompt")
def codex_oauth_test(prompt: str) -> None:
    """Send a tiny test prompt through the selected Codex OAuth mode."""
    from src.core.codex_oauth import cli_adapter
    from src.core.codex_oauth.bridge import validate_bridge_mode
    from src.core.codex_oauth.safety import (
        CodexOAuthConfigError,
        redact_secrets,
        validate_prompt_length,
    )

    try:
        if not settings.codex_oauth_testing_enabled:
            raise CodexOAuthConfigError("Codex OAuth testing is disabled.")

        validate_prompt_length(prompt, settings.codex_max_prompt_chars)

        if settings.codex_oauth_mode == "openai_compatible_bridge":
            from src.core.llm_provider_docker import LLMRouter

            validate_bridge_mode(settings, require_settings_provider=True)
            router = LLMRouter(provider="openai")
            response = router.complete(
                [{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=80,
            )
        elif settings.codex_oauth_mode == "codex_cli":
            response = cli_adapter.run_prompt(prompt, settings)
        else:
            raise CodexOAuthConfigError(
                "CODEX_OAUTH_MODE must be openai_compatible_bridge or codex_cli."
            )

        console.print(f"[bold green]Success![/bold green]\n{response[:1000]}")
    except Exception as e:
        console.print(f"[bold red]Failed:[/bold red] {redact_secrets(e)}")
        raise click.Abort() from None


@codex_oauth.command(name="bridge")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8787, type=int, show_default=True)
def codex_oauth_bridge(host: str, port: int) -> None:
    """Start the local OpenAI-compatible Codex OAuth bridge."""
    import uvicorn

    from src.core.codex_oauth.openai_bridge import create_app

    console.print(
        f"[bold green]Starting Codex OAuth bridge[/bold green] http://{host}:{port}/v1"
    )
    uvicorn.run(create_app(settings), host=host, port=port)


@cli.command()
@click.argument("story_id")
def diagnostics(story_id: str) -> None:
    """Retrieve retrieval and analysis diagnostics for a story.

    Shows candidate census, bucket lane attempts, coverage metrics,
    and visual evidence limitations for the given story.
    """
    import json

    from src.services import AnalysisService

    service = AnalysisService()
    result = service.get_diagnostics(story_id)
    if not result:
        console.print(
            f"[bold red]Error:[/bold red] No diagnostics found for {story_id}"
        )
        raise click.Abort()

    console.print(Panel(f"[bold]Diagnostics for story:[/bold] {story_id[:8]}"))

    # Coverage summary
    coverage = result.get("coverage", {})
    if coverage:
        cov_table = Table(title="Coverage Summary")
        cov_table.add_column("Metric", style="cyan")
        cov_table.add_column("Value", style="white")
        cov_table.add_row("Retained", str(coverage.get("retained_count", 0)))
        cov_table.add_row("Probed", str(coverage.get("probed_count", 0)))
        cov_table.add_row(
            "Coverage Satisfied", str(coverage.get("coverage_satisfied", False))
        )
        cov_table.add_row("Left Count", str(coverage.get("left_count", 0)))
        cov_table.add_row("Center Count", str(coverage.get("center_count", 0)))
        cov_table.add_row("Right Count", str(coverage.get("right_count", 0)))
        missing = coverage.get("missing_buckets", [])
        cov_table.add_row("Missing Buckets", ", ".join(missing) if missing else "none")
        console.print(cov_table)

    # Analysis run info
    run_info = result.get("analysis_run")
    if run_info:
        run_table = Table(title="Analysis Run")
        run_table.add_column("Field", style="cyan")
        run_table.add_column("Value", style="white")
        run_table.add_row("Status", str(run_info.get("status", "N/A")))
        run_table.add_row("Started", str(run_info.get("started_at", "N/A")))
        run_table.add_row("Completed", str(run_info.get("completed_at", "N/A")))
        if run_info.get("error"):
            run_table.add_row("Error", str(run_info["error"]))
        console.print(run_table)

        # Show per-run options used
        opts = run_info.get("options_snapshot", {})
        if opts:
            opts_table = Table(title="Analysis Options (per-run snapshot)")
            opts_table.add_column("Option", style="cyan")
            opts_table.add_column("Value", style="white")
            for key, value in sorted(opts.items()):
                opts_table.add_row(key, str(value))
            console.print(opts_table)

    # Candidate census
    census = result.get("candidate_census", {})
    if census:
        console.print("\n[bold]Candidate Census:[/bold]")
        console.print(json.dumps(census, indent=2, default=str)[:2000])

    # Retrieval candidates
    candidates = result.get("retrieval_candidates", [])
    if candidates:
        cand_table = Table(title=f"Retrieval Candidates ({len(candidates)})")
        cand_table.add_column("URL", style="dim", max_width=40)
        cand_table.add_column("State", style="green")
        cand_table.add_column("Bucket", style="cyan")
        cand_table.add_column("Score", style="white")
        for c in candidates[:20]:
            cand_table.add_row(
                str(c.get("url", ""))[:40],
                str(c.get("state", "")),
                str(c.get("bucket_label", "")),
                str(c.get("relevance_score", ""))[:6],
            )
        console.print(cand_table)
        if len(candidates) > 20:
            console.print(f"[dim]... and {len(candidates) - 20} more candidates[/dim]")

    # Visual evidence summary
    visual = result.get("visual_evidence", {})
    if visual:
        records = visual.get("records", [])
        limitations = visual.get("limitations", [])
        if records or limitations:
            console.print(f"\n[bold]Visual Evidence:[/bold] {len(records)} record(s)")
            if limitations:
                for lim in limitations[:5]:
                    console.print(f"  [yellow]Limitation:[/yellow] {lim}")

    # Report validation warnings
    warnings = result.get("report_validation_warnings", [])
    if warnings:
        console.print(f"\n[bold]Report Validation Warnings ({len(warnings)}):[/bold]")
        for w in warnings[:10]:
            console.print(f"  [yellow]- {w}[/yellow]")

    # Query expansion diagnostics
    qed = result.get("query_expansion_diagnostics", {})
    if qed:
        console.print("\n[bold]Query Expansion:[/bold]")
        console.print(json.dumps(qed, indent=2, default=str)[:1000])


@cli.command()
@click.option(
    "--strict",
    is_flag=True,
    help="Exit with an error when any readiness check is warning or failing.",
)
def health(strict: bool) -> None:
    """Check readiness for configured providers and optional backends."""
    rows = _health_rows()
    status_style = {"ok": "green", "warn": "yellow", "error": "red"}

    table = Table(title="Research Agent Health")
    table.add_column("Component", style="cyan")
    table.add_column("Status")
    table.add_column("Detail", style="white", max_width=70)
    table.add_column("Action", style="dim", max_width=60)

    for component, status, detail, action in rows:
        table.add_row(
            component,
            f"[{status_style.get(status, 'white')}]{status.upper()}[/]",
            detail,
            action,
        )

    console.print(table)

    errors = [row for row in rows if row[1] == "error"]
    warnings = [row for row in rows if row[1] == "warn"]
    if errors:
        console.print(
            f"[bold red]Health check failed:[/bold red] {len(errors)} error(s)"
        )
        raise click.Abort() from None
    if strict and warnings:
        console.print(
            f"[bold yellow]Health check has warnings:[/bold yellow] {len(warnings)} warning(s)"
        )
        raise click.Abort() from None
    console.print("[bold green]Health check completed.[/bold green]")


@cli.command(name="validate-ocr")
@click.option(
    "--fixtures",
    type=click.Path(path_type=Path),
    default=DEFAULT_OCR_FIXTURE_DIR,
    help="Directory containing OCR fixture images and expectations.json.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
)
@click.option(
    "--force",
    is_flag=True,
    help="Run validation even when SCREENSHOT_OCR_ENABLED is false.",
)
def validate_ocr(fixtures: Path, output_format: str, force: bool) -> None:
    """Validate screenshot OCR against repo-owned fixture images."""
    if not settings.screenshot_ocr_enabled and not force:
        console.print(
            "[bold red]OCR validation skipped:[/bold red] "
            "SCREENSHOT_OCR_ENABLED=false. Re-run with --force to validate setup."
        )
        raise click.Abort() from None

    report = validate_ocr_fixtures(fixtures)
    if output_format == "json":
        console.print(json.dumps(report, indent=2, sort_keys=True))
    else:
        console.print(_format_ocr_validation_markdown(report))
    if report["status"] != "passed":
        raise click.Abort() from None


@cli.command()
@click.option(
    "--fixtures",
    type=click.Path(path_type=Path),
    default=Path("tests/fixtures/benchmarks"),
    help="Benchmark fixture directory.",
)
@click.option("--live", is_flag=True, help="Run fixture seeds through AnalysisService.")
@click.option(
    "--live-limit", type=int, default=None, help="Limit live fixture attempts."
)
@click.option(
    "--diagnostics-story-id",
    multiple=True,
    help="Include persisted diagnostics for a story ID. May be repeated.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json", "html"]),
    default="markdown",
)
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.option("--baseline", type=click.Path(path_type=Path), default=None)
@click.option(
    "--fail-on-regression",
    is_flag=True,
    help="Exit non-zero when live/fixture/baseline quality checks fail.",
)
def benchmark(
    fixtures: Path,
    live: bool,
    live_limit: int | None,
    diagnostics_story_id: tuple[str, ...],
    output_format: str,
    output: Path | None,
    baseline: Path | None,
    fail_on_regression: bool,
) -> None:
    """Run retrieval quality benchmarks and optional live pipeline checks."""
    from scripts.run_retrieval_benchmark import (
        apply_baseline,
        format_html,
        format_markdown,
        load_baseline,
        run_benchmarks,
        run_combined_benchmark,
    )

    report = (
        run_combined_benchmark(
            fixtures,
            list(diagnostics_story_id),
            live_run=live,
            live_limit=live_limit,
        )
        if live or diagnostics_story_id
        else run_benchmarks(fixtures)
    )
    if baseline:
        try:
            report = apply_baseline(report, load_baseline(baseline))
        except Exception as exc:
            raise click.ClickException(f"Benchmark baseline error: {exc}") from exc

    if output_format == "json":
        content = json.dumps(report, indent=2, sort_keys=True)
    elif output_format == "html":
        content = format_html(report)
    else:
        content = format_markdown(report)

    if output:
        output.write_text(content, encoding="utf-8")
        console.print(f"[bold green]Benchmark written:[/bold green] {output}")
    else:
        console.print(content)

    fixture_report = report.get("fixtures", report)
    diagnostics_report = report.get("diagnostics", {}) if "fixtures" in report else {}
    live_report = report.get("live", {}) if "fixtures" in report else {}
    if fail_on_regression and (
        fixture_report["aggregate"]["failed_fixture_count"]
        or diagnostics_report.get("missing_story_ids")
        or live_report.get("failed_count", 0)
        or report.get("regressions", {}).get("failed_count", 0)
    ):
        raise click.Abort() from None


@cli.command()
@click.option(
    "--fixtures",
    type=click.Path(path_type=Path),
    default=Path("tests/fixtures/benchmarks"),
    help="Benchmark fixture directory.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
)
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.option("--top", type=int, default=15, help="Number of top results to display.")
def sweep(
    fixtures: Path,
    output_format: str,
    output: Path | None,
    top: int,
) -> None:
    """Sweep relevance weight profiles to find optimal configurations.

    Tests multiple weight combinations and passing-score thresholds across
    all benchmark fixtures to identify the best-performing settings.
    """
    from scripts.sweep_relevance_weights import (
        format_sweep_json,
        format_sweep_markdown,
        run_sweep,
    )

    with console.status("[bold green]Running weight sweep..."):
        results = run_sweep(fixtures)

    if output_format == "json":
        content = format_sweep_json(results)
    else:
        content = format_sweep_markdown(results, top_n=top)

    if output:
        output.write_text(content, encoding="utf-8")
        console.print(f"[bold green]Sweep written:[/bold green] {output}")
    else:
        console.print(content)


@cli.command()
@click.argument("story_id")
@click.argument("stage")
def handoff(story_id: str, stage: str) -> None:
    """Retrieve a persisted agent handoff bundle for a story and stage.

    Stages: post_retrieval, pre_crew, fact_handoff, rhetoric_handoff, narrative_handoff
    """
    import json

    from src.services import AnalysisService

    service = AnalysisService()
    result = service.get_handoff(story_id, stage)
    if not result:
        console.print(
            f"[bold red]Error:[/bold red] No handoff found for {story_id[:8]} / {stage}"
        )
        raise click.Abort()

    console.print(Panel(f"[bold]Handoff:[/bold] {stage} for story {story_id[:8]}"))

    table = Table()
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Stage", result.get("stage", ""))
    table.add_row("From Agent", result.get("from_agent", ""))
    table.add_row("To Agent", result.get("to_agent", ""))
    table.add_row("Created", str(result.get("created_at", "")))
    table.add_row("Summary", str(result.get("summary", ""))[:200])
    console.print(table)

    payload = result.get("payload")
    if payload:
        console.print("\n[bold]Payload:[/bold]")
        console.print(json.dumps(payload, indent=2, default=str)[:3000])


@cli.command(name="test-llm")
@click.option(
    "--provider", "-p", default=None, help="Provider to test (overrides LLM_PROVIDER)"
)
def test_llm(provider: str | None) -> None:
    """Test LLM connection and configuration."""
    from src.core.llm_provider_docker import LLMRouter

    try:
        router = LLMRouter(provider=provider)

        console.print(
            Panel(
                f"[bold]Testing LLM Provider[/bold]\n\nProvider: {router.provider.value}\nModel: {router.model}\nLiteLLM String: {router.litellm_model}"
            )
        )

        with console.status("[bold green]Sending test message..."):
            response = router.complete(
                [
                    {
                        "role": "user",
                        "content": "Say 'Hello from Research Agent!' in exactly those words.",
                    }
                ],
                max_tokens=50,
            )

        console.print(
            f"\n[bold green]✓ Success![/bold green]\nResponse: {response[:200]}"
        )
    except Exception as e:
        console.print(f"[bold red]✗ Failed:[/bold red] {e}")
        raise click.Abort() from None


@cli.command()
def init() -> None:
    """Initialize the database and verify configuration."""

    migrated, migration_detail = run_alembic_upgrade()
    init_db()
    console.print("[bold green]OK[/bold green] Database initialized")
    if migrated:
        console.print(f"[bold green]OK[/bold green] {migration_detail}")
    else:
        console.print(f"[yellow]![/yellow] {migration_detail}")
        console.print("[dim]Used startup schema sync fallback.[/dim]")

    # Check config files
    if settings.channel_profile_path.exists():
        console.print("[bold green]OK[/bold green] Channel profile found")
    else:
        console.print(
            "[yellow]![/yellow] Channel profile not found at config/channel_profile.yaml"
        )

    # Check LLM provider
    provider = settings.llm_provider
    console.print(f"[bold cyan]LLM Provider:[/bold cyan] {provider}")

    # Check for API key based on provider
    key_check = {
        "openrouter": settings.openrouter_api_key,
        "gemini": settings.google_api_key,
        "anthropic": settings.anthropic_api_key,
        "groq": settings.groq_api_key,
        "openai": settings.openai_api_key,
        "lmstudio": "local",  # Optional key, local endpoint
        "grok": settings.xai_api_key,
        "cerebras": settings.cerebras_api_key,
        "sambanova": settings.sambanova_api_key,
        "ollama": "local",  # No key needed
    }

    if key_check.get(provider):
        console.print(f"[bold green]OK[/bold green] API key configured for {provider}")
    else:
        console.print(
            f"[yellow]![/yellow] API key not set for {provider} (add to .env)"
        )

    console.print("\n[bold]Ready to use:[/bold]")
    console.print("  research-agent discover")
    console.print("  research-agent analyze --describe 'story description'")
    console.print("  research-agent profile show")
    console.print("  research-agent test-llm")


if __name__ == "__main__":
    cli()
