"""CLI commands for WeChat Official Accounts (微信公众号)."""
import json
import logging
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...core.cookies import import_cookies as _import_cookies
from ...core.display import console, display_auth_status, display_saved
from ...core.storage import JSONStorage
from .config import (
    AUTH_COOKIE_NAMES,
    COOKIES_FILE,
    SOURCE_NAME,
    get_cookies_from_file,
)
from .scrapers import ArticleScraper, MPPlatformScraper

app = typer.Typer(
    name=SOURCE_NAME,
    help="WeChat Official Accounts (微信公众号) — search accounts & fetch articles.",
    no_args_is_help=True,
)


def _safe_filename(text: str) -> str:
    slug = re.sub(r'[<>:"/\\|?*\s]+', "_", text)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or "untitled"


def _get_scraper(token: Optional[str] = None) -> MPPlatformScraper:
    """Create MPPlatformScraper, raising Exit if not configured."""
    cookies = get_cookies_from_file()
    scraper = MPPlatformScraper(token=token, cookies=cookies)
    if not scraper.is_configured():
        console.print("[red]Not authenticated. Import cookies first:[/red]")
        console.print("  scraper wechat import-cookies <cookies.txt>")
        raise typer.Exit(1)
    return scraper


# =============================================================================
# Status
# =============================================================================


@app.command()
def status() -> None:
    """Check WeChat MP platform authentication status."""
    cookies = get_cookies_from_file()
    cookie_names = set(cookies.keys())
    has_auth = bool(cookie_names & AUTH_COOKIE_NAMES)

    if not has_auth:
        display_auth_status(
            "WeChat MP",
            "logged_out",
            state_file=COOKIES_FILE,
        )
        console.print(
            "\n[dim]Import cookies with:[/dim] "
            "scraper wechat import-cookies <cookies.txt>"
        )
        console.print(
            "[dim]Also need --token from URL:[/dim] "
            "scraper wechat search <query> --token <token>"
        )
        return

    extras = {
        "Cookies": f"{len(cookies)} entries",
        "bizuin": cookies.get("bizuin", "N/A"),
    }
    slave_user = cookies.get("slave_user", "")
    if slave_user:
        extras["Account"] = slave_user

    display_auth_status("WeChat MP", "logged_in", extras=extras, state_file=COOKIES_FILE)
    console.print("\n[dim]Note: Also need --token from URL parameter for API calls[/dim]")


# =============================================================================
# Import Cookies
# =============================================================================


@app.command("import-cookies")
def import_cookies_cmd(
    cookies_path: str = typer.Argument(..., help="Path to Netscape-format cookies.txt"),
) -> None:
    """Import cookies from browser export (Netscape format).

    Export cookies from mp.weixin.qq.com using browser extension
    (EditThisCookie, Cookie-Editor, etc.) in Netscape format.
    """
    try:
        _import_cookies(cookies_path, SOURCE_NAME)
    except FileNotFoundError:
        console.print(f"[red]File not found:[/red] {cookies_path}")
        raise typer.Exit(1)

    cookies = get_cookies_from_file()
    cookie_names = set(cookies.keys())
    has_auth = bool(cookie_names & AUTH_COOKIE_NAMES)

    if has_auth:
        console.print(f"[green]Cookies imported ({len(cookies)} entries)[/green]")
    else:
        console.print("[yellow]Warning: No auth cookies found (slave_sid, bizuin, data_ticket)[/yellow]")


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
# Search (account → articles)
# =============================================================================


@app.command()
def search(
    query: str = typer.Argument(..., help="公众号名称 or WeChat ID"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Session token (auto-detected if omitted)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max articles to fetch"),
    keyword: Optional[str] = typer.Option(None, "--keyword", "-k", help="Filter articles by title keyword"),
    full: bool = typer.Option(False, "--full", "-f", help="Fetch full article content via URL"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save to JSON file"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't auto-save results"),
) -> None:
    """Search for a public account and fetch its articles.

    First searches for the account by name, then fetches its article list.
    Use --full to also fetch full article content (Markdown) for each result.

    Examples:
      scraper wechat search "机器之心"
      scraper wechat search "机器之心" -n 10 --full
      scraper wechat search "机器之心" -k "GPT"
    """
    scraper = _get_scraper(token or None)

    # Step 1: Search for the account
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"Searching account '{query}'...", total=None)
        try:
            accounts = scraper.search_account(query)
        except Exception as e:
            console.print(f"\n[red]Error:[/red] {e}")
            raise typer.Exit(1)

    if not accounts:
        console.print("[yellow]No accounts found[/yellow]")
        return

    # Display accounts and pick the first match
    console.print(f"\n[bold]Found {len(accounts)} account(s):[/bold]\n")
    for i, acct in enumerate(accounts, 1):
        verified = " [green]✓[/green]" if acct.verify_status == 2 else ""
        stype = "订阅号" if acct.service_type == 1 else ("服务号" if acct.service_type == 2 else "未知")
        console.print(f"  {i}. [cyan]{acct.nickname}[/cyan]{verified}  ({stype})")
        if acct.alias:
            console.print(f"     微信号: {acct.alias}")
        if acct.signature:
            console.print(f"     [dim]{acct.signature}[/dim]")

    # Use first account
    target = accounts[0]
    console.print(f"\n[bold]Fetching articles from: {target.nickname}[/bold]")

    # Step 2: Fetch articles
    all_articles = []
    begin = 0
    page_size = 5

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching articles...", total=None)

        while len(all_articles) < limit:
            try:
                if keyword:
                    resp = scraper.search_articles(
                        fakeid=target.fakeid,
                        query=keyword,
                        count=page_size,
                        begin=begin,
                    )
                else:
                    resp = scraper.get_articles(
                        fakeid=target.fakeid,
                        count=page_size,
                        begin=begin,
                    )
            except Exception as e:
                console.print(f"\n[red]Error:[/red] {e}")
                break

            if not resp.articles:
                break

            all_articles.extend(resp.articles)
            begin += page_size

            progress.update(
                task,
                description=f"Fetching articles... ({len(all_articles)}/{resp.total_count})",
            )

            # Stop if we've exhausted all pages
            if keyword:
                if begin >= resp.total_count:
                    break
            else:
                if begin >= resp.publish_count:
                    break

    all_articles = all_articles[:limit]

    if not all_articles:
        console.print("[yellow]No articles found[/yellow]")
        return

    # Step 3 (optional): Fetch full content
    full_articles = []
    if full:
        article_scraper = ArticleScraper()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching full content...", total=len(all_articles))
            for i, brief in enumerate(all_articles):
                if not brief.link:
                    progress.update(task, advance=1)
                    continue
                try:
                    fa = article_scraper.fetch(brief.link)
                    full_articles.append(fa)
                    progress.update(
                        task, advance=1,
                        description=f"Fetching full content... ({i+1}/{len(all_articles)})",
                    )
                except Exception as e:
                    logger.warning("Failed to fetch %s: %s", brief.link, e)
                    progress.update(task, advance=1)

    # Display results
    console.print(f"\n[bold]Found {len(all_articles)} articles[/bold]\n")

    for i, article in enumerate(all_articles, 1):
        title = article.clean_title
        if len(title) > 80:
            title = title[:80] + "..."

        console.print(f"[dim]{i:3}.[/dim] [bold]{title}[/bold]")

        meta_parts = []
        if article.update_datetime:
            meta_parts.append(f"[green]{article.update_datetime.strftime('%Y-%m-%d %H:%M')}[/green]")
        if article.author_name:
            meta_parts.append(f"[cyan]{article.author_name}[/cyan]")
        if article.copyright_type == 1:
            meta_parts.append("[yellow]原创[/yellow]")
        if article.link:
            meta_parts.append(f"[dim]{article.link[:70]}[/dim]")

        if meta_parts:
            console.print(f"     {'  '.join(meta_parts)}")

        if article.digest:
            digest = article.digest[:100] + ("..." if len(article.digest) > 100 else "")
            console.print(f"     [dim]{digest}[/dim]")

        console.print()

    if full and full_articles:
        console.print(f"[bold]Fetched full content for {len(full_articles)}/{len(all_articles)} articles[/bold]\n")

    # Save
    if full and full_articles:
        data = {
            "account": target.model_dump(mode="json"),
            "articles": [a.model_dump(mode="json") for a in full_articles],
            "query": query,
            "keyword": keyword,
        }
    else:
        data = {
            "account": target.model_dump(mode="json"),
            "articles": [a.model_dump(mode="json") for a in all_articles],
            "query": query,
            "keyword": keyword,
        }

    if output:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        display_saved(output)
    elif not no_save:
        storage = JSONStorage(source=SOURCE_NAME)
        slug = _safe_filename(target.nickname)
        path = storage.save(data, f"account_{slug}.json", description="articles")
        display_saved(path)


# =============================================================================
# Fetch (single article by URL)
# =============================================================================


@app.command()
def fetch(
    url: str = typer.Argument(..., help="WeChat article URL (mp.weixin.qq.com/s/...)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save to JSON file"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't auto-save results"),
    show_content: bool = typer.Option(False, "--content", "-c", help="Show full content"),
) -> None:
    """Fetch a WeChat article by URL.

    Examples:
      scraper wechat fetch "https://mp.weixin.qq.com/s/xxxxx"
      scraper wechat fetch "https://mp.weixin.qq.com/s/xxxxx" -c
    """
    scraper = ArticleScraper()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Fetching article...", total=None)
        try:
            article = scraper.fetch(url)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    # Display
    console.print()
    console.print(f"[bold]{article.title}[/bold]")
    console.print(f"[cyan]{article.account_name}[/cyan]", end="")
    if article.publish_time:
        console.print(f"  [green]{article.publish_time.strftime('%Y-%m-%d %H:%M')}[/green]", end="")
    console.print()

    if article.description:
        console.print(f"[dim]{article.description}[/dim]")

    if article.images:
        console.print(f"[magenta]Images: {len(article.images)}[/magenta]")

    console.print(f"[dim]{article.url}[/dim]")

    if show_content:
        console.print(f"\n{'─' * 60}\n")
        console.print(article.content)

    # Save
    if output:
        data = article.model_dump(mode="json")
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        display_saved(output)
    elif not no_save:
        storage = JSONStorage(source=SOURCE_NAME)
        slug = _safe_filename(article.title)
        data = article.model_dump(mode="json")
        path = storage.save(data, f"article_{slug}.json", description="article")
        display_saved(path)


# =============================================================================
# Batch fetch
# =============================================================================


@app.command("batch")
def batch_fetch(
    file: str = typer.Argument(..., help="Text file with one URL per line"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save to JSON file"),
) -> None:
    """Batch fetch articles from a URL list file.

    Examples:
      scraper wechat batch urls.txt
      scraper wechat batch urls.txt -o articles.json
    """
    try:
        with open(file, "r") as f:
            urls = [line.strip() for line in f if line.strip() and "mp.weixin.qq.com" in line]
    except FileNotFoundError:
        console.print(f"[red]File not found:[/red] {file}")
        raise typer.Exit(1)

    if not urls:
        console.print("[yellow]No valid WeChat URLs found in file[/yellow]")
        raise typer.Exit(1)

    console.print(f"Found {len(urls)} URLs")

    scraper = ArticleScraper()
    articles = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching...", total=len(urls))
        for i, url in enumerate(urls):
            try:
                article = scraper.fetch(url)
                articles.append(article)
                progress.update(task, advance=1, description=f"Fetched ({i+1}/{len(urls)}): {article.title[:30]}")
            except Exception as e:
                progress.update(task, advance=1, description=f"Failed ({i+1}/{len(urls)}): {e}")

    console.print(f"\n[bold]Success: {len(articles)}/{len(urls)}[/bold]")

    for i, article in enumerate(articles, 1):
        console.print(f"  {i}. [cyan]{article.account_name}[/cyan] — {article.title[:50]}")

    # Save
    if articles:
        data = [a.model_dump(mode="json") for a in articles]
        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            display_saved(output)
        else:
            storage = JSONStorage(source=SOURCE_NAME)
            path = storage.save(data, "batch_articles.json", description="articles")
            display_saved(path)
