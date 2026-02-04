"""CLI entry point for Research Agent."""

from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.core.config import settings
from src.database import init_db

console = Console()


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


@click.group()
@click.version_option(version="0.1.0", prog_name="research-agent")
def cli() -> None:
    """Research Agent - AI-powered news research for YouTube creators.

    Find relevant stories, analyze political bias across sources,
    separate facts from opinions, and generate content outlines.
    """
    # Initialize database on startup
    init_db()


@cli.command()
@click.option("--count", "-n", default=10, help="Number of stories to discover")
@click.option("--topics", "-t", multiple=True, help="Topic keywords to search")
def discover(_count: int, topics: tuple[str, ...]) -> None:
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
            result = service.discover(topic_list)
            console.print("\n[bold green]Discovery Complete![/bold green]\n")
            console.print(result.get("raw_output", "No results"))
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise click.Abort() from None


@cli.command()
@click.option("--url", "-u", default=None, help="URL of story to analyze")
@click.option("--describe", "-d", default=None, help="Description of story to research")
@click.option("--output", "-o", default=None, help="Output file for report (markdown)")
def analyze(url: str | None, describe: str | None, output: str | None) -> None:
    """Analyze a specific story from URL or description.

    Aggregates sources from across the political spectrum,
    classifies bias, separates facts from opinions, and generates a report.
    """
    from src.services import AnalysisService

    if not url and not describe:
        console.print("[bold red]Error:[/bold red] Please provide --url or --describe")
        raise click.Abort()

    story_desc = describe or f"Story from URL: {url}"

    console.print(Panel(f"[bold]Analyzing story:[/bold]\n{story_desc[:200]}"))

    with console.status("[bold green]Running multi-source analysis..."):
        try:
            service = AnalysisService()
            result = service.analyze(story_desc, url)
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


@cli.command(name="test-llm")
@click.option(
    "--provider", "-p", default=None, help="Provider to test (overrides LLM_PROVIDER)"
)
def test_llm(provider: str | None) -> None:
    """Test LLM connection and configuration."""
    from src.core.llm_provider import LLMRouter

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

    init_db()
    console.print("[bold green]✓[/bold green] Database initialized")

    # Check config files
    if settings.channel_profile_path.exists():
        console.print("[bold green]✓[/bold green] Channel profile found")
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
        "grok": settings.xai_api_key,
        "cerebras": settings.cerebras_api_key,
        "sambanova": settings.sambanova_api_key,
        "ollama": "local",  # No key needed
    }

    if key_check.get(provider):
        console.print(f"[bold green]✓[/bold green] API key configured for {provider}")
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
