"""CLI commands for X (Twitter) source."""
import json
import re
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...core.cookies import import_cookies as _import_cookies
from ...core.display import (
    ColumnDef,
    console,
    display_auth_status,
    display_options,
    display_saved,
)
from ...core.storage import JSONStorage
from .config import (
    COOKIES_FILE,
    SEARCH_PRODUCTS,
    SOURCE_NAME,
    get_cookies_from_file,
)
from .scrapers import SearchScraper


def _safe_filename(text: str) -> str:
    slug = re.sub(r'[<>:"/\\|?*\s]+', "_", text)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or "untitled"


app = typer.Typer(
    name=SOURCE_NAME,
    help="X (Twitter) commands — search tweets via GraphQL API.",
    no_args_is_help=True,
)


# =============================================================================
# Status
# =============================================================================


@app.command()
def status() -> None:
    """Check X authentication status (cookies)."""
    cookies = get_cookies_from_file()
    if not cookies.get("auth_token"):
        display_auth_status(
            "X (Twitter)",
            "logged_out",
            state_file=COOKIES_FILE,
        )
        console.print(
            "\n[dim]Import cookies with:[/dim] "
            "scraper x import-cookies <cookies.txt>"
        )
        return

    # Extract user info from twid cookie
    twid = cookies.get("twid", "")
    user_id = twid.replace("u%3D", "") if twid else "unknown"

    display_auth_status(
        "X (Twitter)",
        "logged_in",
        extras={"User ID": user_id, "Cookies": f"{len(cookies)} entries"},
        state_file=COOKIES_FILE,
    )


# =============================================================================
# Import Cookies
# =============================================================================


@app.command("import-cookies")
def import_cookies_cmd(
    cookies_path: str = typer.Argument(..., help="Path to Netscape-format cookies.txt"),
) -> None:
    """Import cookies from browser export (Netscape format)."""
    try:
        _import_cookies(cookies_path, SOURCE_NAME)
    except FileNotFoundError:
        console.print(f"[red]File not found:[/red] {cookies_path}")
        raise typer.Exit(1)

    cookies = get_cookies_from_file()
    if cookies.get("auth_token"):
        console.print(f"[green]Cookies imported ({len(cookies)} entries)[/green]")
    else:
        console.print("[yellow]Warning: No auth_token found in cookies file[/yellow]")


# =============================================================================
# Logout
# =============================================================================


@app.command()
def logout() -> None:
    """Clear saved cookies."""
    if COOKIES_FILE.exists():
        COOKIES_FILE.unlink()
        console.print("[green]Cookies cleared[/green]")
    else:
        console.print("[dim]No cookies to clear[/dim]")


# =============================================================================
# Options
# =============================================================================


@app.command()
def options() -> None:
    """Show available search options."""
    display_options(
        items=[
            {"option": "Product (--product)", "values": ", ".join(SEARCH_PRODUCTS)},
        ],
        columns=[
            ColumnDef("Option", "option", style="cyan"),
            ColumnDef("Values", "values"),
        ],
        title="X Search Options",
    )
    console.print("\n[bold]Advanced search options:[/bold]")
    console.print("  --exact TEXT        Exact phrase match")
    console.print("  --any TEXT          Any of these words (OR)")
    console.print("  --exclude TEXT      Exclude these words")
    console.print("  --hashtags TEXT     Include hashtags")
    console.print("  --from USER        Tweets from this user")
    console.print("  --to USER          Replies to this user")
    console.print("  --mention USER     Mentioning this user")
    console.print("  --min-likes N      Minimum likes")
    console.print("  --min-retweets N   Minimum retweets")
    console.print("  --min-replies N    Minimum replies")
    console.print("  --since YYYY-MM-DD From date")
    console.print("  --until YYYY-MM-DD To date")
    console.print("  --lang CODE        Language (en, zh, ja, ...)")
    console.print("  --filter TYPE      links, images, videos, media")
    console.print("  --exclude-filter   e.g. replies")
    console.print("\n[bold]Inline query syntax (also supported):[/bold]")
    console.print("  from:user  to:user  since:2024-01-01  min_faves:100")
    console.print("  filter:links  -filter:replies  lang:en")


# =============================================================================
# Search
# =============================================================================


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (all of these words, use '' for advanced-only)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max tweets to fetch"),
    product: str = typer.Option(
        "Top", "--product", "-p",
        help="Search type: Top, Latest, People, Photos, Videos",
    ),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save to JSON file"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't auto-save results"),
    # Advanced search options
    exact_phrase: Optional[str] = typer.Option(None, "--exact", help="Exact phrase match"),
    any_words: Optional[str] = typer.Option(None, "--any", help="Any of these words (OR)"),
    exclude_words: Optional[str] = typer.Option(None, "--exclude", help="Exclude these words"),
    hashtags: Optional[str] = typer.Option(None, "--hashtags", help="Include hashtags"),
    from_user: Optional[str] = typer.Option(None, "--from", help="From this user"),
    to_user: Optional[str] = typer.Option(None, "--to", help="Replies to this user"),
    mention: Optional[str] = typer.Option(None, "--mention", help="Mentioning this user"),
    min_likes: Optional[int] = typer.Option(None, "--min-likes", help="Minimum likes"),
    min_retweets: Optional[int] = typer.Option(None, "--min-retweets", help="Minimum retweets"),
    min_replies: Optional[int] = typer.Option(None, "--min-replies", help="Minimum replies"),
    since: Optional[str] = typer.Option(None, "--since", help="From date (YYYY-MM-DD)"),
    until: Optional[str] = typer.Option(None, "--until", help="To date (YYYY-MM-DD)"),
    lang: Optional[str] = typer.Option(None, "--lang", help="Language code (e.g. en, zh)"),
    filter_type: Optional[str] = typer.Option(None, "--filter", help="Filter: links, images, videos, media"),
    exclude_filter: Optional[str] = typer.Option(None, "--exclude-filter", help="Exclude filter (e.g. replies)"),
) -> None:
    """Search tweets on X (Twitter) with advanced search options.

    Examples:
      scraper x search "Claude AI" -n 10
      scraper x search "from:elonmusk" --product Latest
      scraper x search "AI" --from openai --min-likes 100 --since 2026-01-01
      scraper x search --exact "artificial intelligence" --lang en
      scraper x search "AI" --exclude "ChatGPT" --filter images
    """
    if product not in SEARCH_PRODUCTS:
        console.print(f"[red]Invalid product. Choose from: {', '.join(SEARCH_PRODUCTS)}[/red]")
        raise typer.Exit(1)

    # Build advanced search kwargs
    adv_kwargs = {
        "exact_phrase": exact_phrase,
        "any_words": any_words,
        "exclude_words": exclude_words,
        "hashtags": hashtags,
        "from_user": from_user,
        "to_user": to_user,
        "mention": mention,
        "min_likes": min_likes,
        "min_retweets": min_retweets,
        "min_replies": min_replies,
        "since": since,
        "until": until,
        "lang": lang,
        "filter": filter_type,
        "exclude_filter": exclude_filter,
    }
    # Remove None values
    adv_kwargs = {k: v for k, v in adv_kwargs.items() if v is not None}

    if not query and not adv_kwargs:
        console.print("[red]Provide a query or at least one advanced search option[/red]")
        raise typer.Exit(1)

    scraper = SearchScraper()
    if not scraper.is_configured():
        console.print("[red]Not authenticated. Import cookies first:[/red]")
        console.print("  scraper x import-cookies <cookies.txt>")
        raise typer.Exit(1)

    all_tweets = []
    cursor = None
    pages = 0
    max_pages = (limit + 19) // 20  # ceil division

    # Build display query for progress
    from .scrapers.search import build_query
    display_query = build_query(query, **adv_kwargs)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Searching '{display_query}'...", total=None)

        while len(all_tweets) < limit and pages < max_pages:
            try:
                resp = scraper.search(
                    query=query,
                    count=20,
                    product=product,
                    cursor=cursor,
                    **adv_kwargs,
                )
            except Exception as e:
                console.print(f"\n[red]Error:[/red] {e}")
                break

            all_tweets.extend(resp.tweets)
            cursor = resp.cursor_bottom
            pages += 1

            progress.update(
                task,
                description=f"Searching '{query}'... ({len(all_tweets)} tweets)",
            )

            if not cursor or not resp.tweets:
                break

    all_tweets = all_tweets[:limit]

    if not all_tweets:
        console.print("[yellow]No results found[/yellow]")
        return

    console.print(f"\n[bold]Found {len(all_tweets)} tweets[/bold]\n")

    # Display results
    for i, tweet in enumerate(all_tweets, 1):
        author_str = ""
        if tweet.author:
            author_str = f"[cyan]@{tweet.author.screen_name}[/cyan] "

        # Truncate text for display
        text = tweet.full_text.replace("\n", " ")
        if len(text) > 200:
            text = text[:200] + "..."

        console.print(f"[dim]{i:3}.[/dim] {author_str}[bold]{text}[/bold]")

        stats = []
        if tweet.view_count:
            stats.append(f"views:{tweet.view_count}")
        stats.append(f"likes:{tweet.favorite_count}")
        stats.append(f"rt:{tweet.retweet_count}")
        stats.append(f"replies:{tweet.reply_count}")

        meta_parts = [f"[yellow]{' | '.join(stats)}[/yellow]"]
        if tweet.created_at:
            meta_parts.append(f"[green]{tweet.created_at}[/green]")
        if tweet.url:
            meta_parts.append(f"[dim]{tweet.url}[/dim]")

        console.print(f"     {'  '.join(meta_parts)}")

        if tweet.media_urls:
            console.print(f"     [magenta]media: {len(tweet.media_urls)} item(s)[/magenta]")

        console.print()

    # Save
    if output:
        data = [t.model_dump(mode="json") for t in all_tweets]
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        display_saved(output)
    elif not no_save:
        storage = JSONStorage(source=SOURCE_NAME)
        slug = _safe_filename(query)
        data = [t.model_dump(mode="json") for t in all_tweets]
        path = storage.save(data, f"search_{slug}.json", description="tweets")
        display_saved(path)


if __name__ == "__main__":
    app()
