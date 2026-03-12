"""CLI commands for JD (京东) scraper."""
import json
from pathlib import Path
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ...core.display import (
    ColumnDef,
    console,
    display_auth_status,
    display_detail,
    display_saved,
    display_search_results,
)
from ...core.storage import JSONStorage
from .config import SOURCE_NAME, AUTH_COOKIES, DEVICE_COOKIES, STOCK_STATE
from .cookies import (
    get_cookies_path,
    load_cookies,
    validate_cookies,
    check_cookies_valid_sync,
    get_username_from_cookies,
    get_area_from_cookies,
    get_eid_token,
)

app = typer.Typer(
    name=SOURCE_NAME,
    help="京东 (JD.com) product scraping commands.",
    no_args_is_help=True,
)


# =============================================================================
# Cookie Management
# =============================================================================


@app.command("import-cookies")
def import_cookies(
    source: Path = typer.Argument(..., help="Source cookies.txt file (Netscape format)"),
) -> None:
    """Import cookies.txt to the standard location."""
    if not source.exists():
        console.print(f"[red]Error:[/red] File not found: {source}")
        raise typer.Exit(1)

    dest = get_cookies_path()
    dest.parent.mkdir(parents=True, exist_ok=True)

    import shutil
    shutil.copy(source, dest)

    # Validate imported cookies
    try:
        cookies = load_cookies(dest)
    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Could not parse cookies: {e}")
        console.print(f"[green]✓[/green] File copied to {dest}")
        return

    cookie_count = len(list(cookies.jar))
    is_valid = validate_cookies(cookies)
    username = get_username_from_cookies(cookies)

    console.print(f"[green]✓[/green] Imported {cookie_count} cookies to {dest}")

    if username:
        console.print(f"  User: [cyan]{username}[/cyan]")

    if not is_valid:
        console.print(
            "[yellow]Warning:[/yellow] Missing required cookies "
            f"({', '.join(AUTH_COOKIES[:3])}). Cookies may not work."
        )


@app.command()
def status(
    cookies_file: Optional[Path] = typer.Option(
        None, "--cookies", "-c", help="Path to cookies.txt file"
    ),
) -> None:
    """Check JD cookie validity and login status."""
    cookies_path = cookies_file or get_cookies_path()

    try:
        cookies = load_cookies(cookies_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]To export cookies:[/yellow]")
        console.print("1. Install browser extension 'cookies.txt' or 'Cookie-Editor'")
        console.print("2. Log in to jd.com")
        console.print("3. Export cookies in Netscape format")
        console.print(f"4. Run: scraper jd import-cookies <path>")
        raise typer.Exit(1)

    cookie_count = len(list(cookies.jar))
    has_required = validate_cookies(cookies)
    username = get_username_from_cookies(cookies)
    area = get_area_from_cookies(cookies)
    eid = get_eid_token(cookies)

    extras = {
        "Cookies": f"{cookie_count} loaded from {cookies_path}",
        "Required cookies": "[green]✓ present[/green]" if has_required else "[red]✗ missing[/red]",
    }
    if username:
        extras["User (pin)"] = username
    if area:
        extras["Area"] = area
    if eid:
        extras["EID Token"] = f"{eid[:20]}..." if len(eid) > 20 else eid

    # Online validation
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Verifying cookies online...", total=None)
        is_valid, message = check_cookies_valid_sync(cookies)

    status_str = "logged_in" if is_valid else "logged_out"
    extras["Online check"] = f"[green]{message}[/green]" if is_valid else f"[red]{message}[/red]"

    display_auth_status(
        source_name="JD (京东)",
        status=status_str,
        extras=extras,
        state_file=cookies_path,
    )

    if not is_valid:
        raise typer.Exit(1)


@app.command()
def search(
    keyword: str = typer.Argument(..., help="Search keyword"),
    limit: int = typer.Option(30, "--limit", "-n", help="Max products to collect"),
    pages: Optional[int] = typer.Option(None, "--pages", "-p", help="Max pages (30 per page)"),
    sort: str = typer.Option("default", "--sort", help="Sort: default, sales, price_asc, price_desc, comments"),
    price: Optional[str] = typer.Option(None, "--price", help="Price range: min-max (e.g. 100-500)"),
    jd_delivery: bool = typer.Option(False, "--jd-delivery", help="JD delivery only"),
    delay: float = typer.Option(1.5, "--delay", "-d", help="Delay between pages (seconds)"),
    cookies_file: Optional[Path] = typer.Option(None, "--cookies", "-c", help="Path to cookies.txt"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save to JSON file"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to data directory"),
) -> None:
    """Search JD products by keyword."""
    from .scrapers import SearchScraper

    try:
        scraper = SearchScraper(cookies_file)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"Searching [cyan]{keyword}[/cyan]...")

    try:
        result = scraper.search(
            keyword,
            max_pages=pages,
            max_results=limit,
            sort=sort,
            price_range=price,
            delivery=jd_delivery,
            delay=delay,
        )
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Display summary
    console.print(
        f"\n[bold]Search: {result.normalized_keyword or keyword}[/bold]  "
        f"Total: [cyan]{result.total_count or '-'}[/cyan]  "
        f"Collected: [bold]{len(result.products)}[/bold]"
    )

    # Display as table
    if result.products:
        rows = []
        for p in result.products:
            rows.append({
                "sku": p.sku_id,
                "name": p.name[:50] + ("..." if len(p.name) > 50 else ""),
                "price": f"¥{p.price}" if p.price else "-",
                "shop": (p.shop_name or "-")[:15],
                "comments": p.comment_count or "-",
                "score": p.average_score or "-",
                "brand": (p.brand or "-")[:10],
            })

        display_search_results(
            results=rows,
            columns=[
                ColumnDef("SKU", "sku", style="dim", width=16),
                ColumnDef("Name", "name", style="bold", max_width=50),
                ColumnDef("Price", "price", style="green", width=10),
                ColumnDef("Shop", "shop", style="cyan", max_width=15),
                ColumnDef("Comments", "comments", style="yellow", width=10),
                ColumnDef("Score", "score", style="magenta", width=5),
                ColumnDef("Brand", "brand", style="dim", max_width=10),
            ],
            title=f"Search: {keyword} ({sort})",
            summary=f"Showing {len(rows)} of {result.total_count or '?'} products",
        )

    # Save
    if output:
        data = result.model_dump(mode="json")
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        display_saved(output, description="Search results")
    elif save and result.products:
        storage = JSONStorage(source=SOURCE_NAME)
        safe_kw = keyword.replace("/", "_").replace(" ", "_")[:30]
        filename = f"search_{safe_kw}.json"
        save_path = storage.save(
            result.model_dump(mode="json"),
            filename,
            description="search results",
        )
        display_saved(save_path, description="Search results")


@app.command()
def fetch(
    url_or_id: str = typer.Argument(..., help="Product URL or SKU ID"),
    comments: bool = typer.Option(True, "--comments/--no-comments", help="Include comment summary"),
    recommendations: bool = typer.Option(False, "--recommendations", "-r", help="Include recommendations"),
    graphic: bool = typer.Option(False, "--graphic", "-g", help="Include graphic detail images"),
    cookies_file: Optional[Path] = typer.Option(
        None, "--cookies", "-c", help="Path to cookies.txt file"
    ),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to data directory"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
) -> None:
    """Fetch product detail from a JD product page."""
    from .scrapers import ProductScraper
    from .scrapers.product import extract_sku_id

    try:
        scraper = ProductScraper(cookies_file)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    sku_id = extract_sku_id(url_or_id)
    console.print(f"Fetching product [cyan]{sku_id}[/cyan]...")

    console.print("Loading product page & intercepting APIs...")
    try:
        product = scraper.scrape(
            url_or_id,
            include_comments=comments,
            include_recommendations=recommendations,
            include_graphic=graphic,
        )
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Display product info
    meta = {
        "SKU ID": product.sku_id,
        "Name": product.name or "-",
        "Price": product.price.current or "-",
        "Final Price": f"{product.price.final} ({product.price.final_label})" if product.price.final else "-",
        "Stock": product.stock_label or product.stock_state or "-",
        "Shop": f"{product.shop.shop_name or '-'} ({'自营' if product.shop.is_self else '第三方'})",
        "URL": product.product_url,
    }

    # Build attribute string
    attr_text = ""
    if product.attributes:
        attr_text = "\n".join(f"  {a.name}: {a.value}" for a in product.attributes[:10])

    display_detail(
        meta=meta,
        content=attr_text,
        title="Product Detail",
        content_title="Attributes",
    )

    # Display SKU dimensions
    if product.sku_dimensions:
        sku_table = Table(title="SKU Variants", show_lines=True)
        sku_table.add_column("Dimension", style="cyan")
        sku_table.add_column("Option", style="bold")
        sku_table.add_column("SKU ID", style="dim")
        sku_table.add_column("Stock", style="yellow")

        for dim in product.sku_dimensions:
            for i, v in enumerate(dim.variants):
                sku_table.add_row(
                    dim.title if i == 0 else "",
                    v.text,
                    v.sku_id,
                    v.stock,
                )
        console.print(sku_table)

    # Display promotions
    if product.promotions:
        console.print("\n[bold]Promotions:[/bold]")
        for p in product.promotions:
            console.print(f"  [magenta]{p.label}[/magenta]: {p.content}")

    # Display comment summary
    comment_data = (product.raw_data or {}).get("comment_summary")
    if comment_data:
        console.print(f"\n[bold]Comments:[/bold] Total: {comment_data.get('total_count', '-')}, "
                      f"Good rate: {comment_data.get('good_rate', '-')}")
        tags = comment_data.get("semantic_tags", [])
        if tags:
            tag_str = ", ".join(f"{t['name']}({t['count']})" for t in tags[:8])
            console.print(f"  Tags: {tag_str}")

    # Display recommendations count
    rec_data = (product.raw_data or {}).get("recommendations")
    if rec_data:
        rec_count = len(rec_data.get("products", []))
        console.print(f"\n[bold]Recommendations:[/bold] {rec_count} products")

    # Save
    if save or output:
        # Remove raw_data for cleaner output (keep comment_summary and recommendations at top level)
        export_data = product.model_dump(mode="json")
        # Extract nested data to top level
        raw = export_data.pop("raw_data", {}) or {}
        if "comment_summary" in raw:
            export_data["comment_summary"] = raw["comment_summary"]
        if "recommendations" in raw:
            export_data["recommendations"] = raw["recommendations"]

        storage = JSONStorage(source=SOURCE_NAME)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            display_saved(output, description="Product")
        elif save:
            filename = f"{product.sku_id}.json"
            save_path = storage.save(export_data, filename, description="product")
            display_saved(save_path, description="Product")


@app.command()
def comments(
    url_or_id: str = typer.Argument(..., help="Product URL or SKU ID"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max comments to collect"),
    pages: Optional[int] = typer.Option(None, "--pages", "-p", help="Max pages (default: all)"),
    score: str = typer.Option("all", "--score", help="Filter: all, good, medium, bad"),
    sort: str = typer.Option("default", "--sort", help="Sort: default, time"),
    pic_only: bool = typer.Option(False, "--pic-only", help="Only comments with pictures"),
    delay: float = typer.Option(1.0, "--delay", "-d", help="Delay between pages (seconds)"),
    cookies_file: Optional[Path] = typer.Option(None, "--cookies", "-c", help="Path to cookies.txt"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save to JSON file"),
    strategy: str = typer.Option("api", "--strategy", "-s", help="Strategy: api (Playwright h5st + httpx, fast), playwright (full browser interception)"),
) -> None:
    """Scrape product comments with pagination.

    Default strategy 'api': Playwright generates h5st signature, httpx fetches data.
    Fallback 'playwright': full browser interception via comment popup scrolling.
    Supports filtering by score, pictures, and sorting.
    """
    from .scrapers import CommentScraper
    from .scrapers.product import extract_sku_id

    sku_id = extract_sku_id(url_or_id)

    try:
        scraper = CommentScraper(cookies_file)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"Scraping comments for [cyan]{sku_id}[/cyan] (strategy: {strategy})...")
    try:
        result = scraper.scrape(
            sku_id,
            max_pages=pages,
            max_comments=limit,
            score=score,
            sort=sort,
            has_picture=pic_only,
            delay=delay,
            strategy=strategy,
        )
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if strategy == "api":
            console.print(
                "\n[yellow]Tip:[/yellow] API mode failed. Try Playwright mode:\n"
                f"  scraper jd comments {url_or_id} --strategy playwright"
            )
        else:
            console.print(
                "\n[yellow]Tip:[/yellow] If you're on an overseas IP, "
                "club.jd.com comment API may be blocked.\n"
                "Use 'scraper jd fetch <sku>' to get 3-5 preview comments via page interception."
            )
        raise typer.Exit(1)

    # Display summary
    console.print(f"\n[bold]Comments for SKU {sku_id}[/bold]")
    console.print(
        f"  Total: [cyan]{result.total_count or '-'}[/cyan]  "
        f"Good: [green]{result.good_count or '-'}[/green]  "
        f"Rate: [green]{result.good_rate or '-'}[/green]  "
        f"With pics: [yellow]{result.pic_count or '-'}[/yellow]"
    )

    if result.semantic_tags:
        tag_str = ", ".join(f"{t.name}({t.count})" for t in result.semantic_tags[:10])
        console.print(f"  Tags: {tag_str}")

    console.print(f"\n  Collected: [bold]{len(result.comments)}[/bold] comments\n")

    # Display as table
    if result.comments:
        rows = []
        for c in result.comments:
            spec_str = ""
            if c.specs:
                spec_parts = []
                for s in c.specs:
                    for k, v in s.items():
                        spec_parts.append(f"{v}")
                spec_str = " / ".join(spec_parts)

            rows.append({
                "score": f"{'★' * int(c.score)}" if c.score and c.score.isdigit() else c.score or "-",
                "date": (c.date or "")[:10],
                "user": c.user_name or "-",
                "area": c.area or "",
                "content": c.content[:60] + ("..." if len(c.content) > 60 else ""),
                "spec": spec_str[:30],
                "pics": str(c.pic_count) if c.pic_count else "",
            })

        display_search_results(
            results=rows,
            columns=[
                ColumnDef("Score", "score", style="yellow", width=7),
                ColumnDef("Date", "date", style="green", width=12),
                ColumnDef("User", "user", style="cyan", max_width=15),
                ColumnDef("Area", "area", style="dim", width=6),
                ColumnDef("Content", "content", style="bold", max_width=60),
                ColumnDef("Spec", "spec", style="dim", max_width=30),
                ColumnDef("Pics", "pics", style="yellow", width=4),
            ],
            title=f"Comments ({score}, {sort})",
            summary=f"Showing {len(rows)} of {result.total_count or '?'} comments",
        )

    # Save
    if output:
        data = result.model_dump(mode="json")
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        display_saved(output, description="Comments")
    elif result.comments:
        storage = JSONStorage(source=SOURCE_NAME)
        filename = f"{sku_id}_comments.json"
        save_path = storage.save(
            result.model_dump(mode="json"),
            filename,
            description="comments",
        )
        display_saved(save_path, description="Comments")


@app.command("batch-comments")
def batch_comments(
    file: Path = typer.Argument(..., help="Search result JSON file (from 'scraper jd search')"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max comments per product"),
    score: str = typer.Option("all", "--score", help="Filter: all, good, medium, bad"),
    sort: str = typer.Option("default", "--sort", help="Sort: default, time"),
    delay: float = typer.Option(2.0, "--delay", "-d", help="Delay between products (seconds)"),
    cookies_file: Optional[Path] = typer.Option(None, "--cookies", "-c", help="Path to cookies.txt"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory (default: exports/)"),
) -> None:
    """Batch scrape comments for products from a search result JSON file.

    Reads a JSON file produced by 'scraper jd search', iterates through
    all products, and scrapes comments for each. Reuses a single browser
    session for efficiency.

    Example:
        scraper jd search '猕猴桃' -n 10
        scraper jd batch-comments ~/.web_scraper/jd/exports/search_猕猴桃.json -n 20
    """
    from .scrapers import CommentScraper

    if not file.exists():
        console.print(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)

    # Load search results
    with open(file, encoding="utf-8") as f:
        data = json.load(f)

    products = data.get("products", [])
    if not products:
        console.print("[yellow]No products found in file.[/yellow]")
        raise typer.Exit(1)

    keyword = data.get("keyword", "")
    console.print(
        f"Loaded [cyan]{len(products)}[/cyan] products from search "
        f"[cyan]{keyword}[/cyan]"
    )

    try:
        scraper = CommentScraper(cookies_file)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Determine output directory
    output_dir = output
    if output_dir is None:
        storage = JSONStorage(source=SOURCE_NAME)
        output_dir = storage.output_dir
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    from .h5st import SignatureOracle
    from .cookies import load_cookies

    http_cookies = load_cookies(scraper.cookies_path)
    succeeded = 0
    failed = 0

    with SignatureOracle(scraper.cookies_path) as oracle:
        for i, product in enumerate(products, 1):
            sku_id = product.get("sku_id", "")
            name = product.get("name", "")[:30]
            if not sku_id:
                continue

            console.print(
                f"\n[dim][{i}/{len(products)}][/dim] "
                f"[cyan]{sku_id}[/cyan] {name}"
            )

            try:
                result = scraper.scrape(
                    sku_id,
                    max_comments=limit,
                    score=score,
                    sort=sort,
                    delay=1.0,
                    strategy="api",
                    oracle=oracle,
                )

                comment_count = len(result.comments)
                total = result.total_count or "?"
                console.print(
                    f"  Got [bold]{comment_count}[/bold] comments "
                    f"(total: {total})"
                )

                if result.comments:
                    save_data = result.model_dump(mode="json")
                    save_data["product_name"] = product.get("name", "")
                    save_data["product_price"] = product.get("price")

                    save_path = output_dir / f"{sku_id}_comments.json"
                    with open(save_path, "w", encoding="utf-8") as f:
                        json.dump(save_data, f, ensure_ascii=False, indent=2)
                    console.print(f"  Saved to {save_path}")

                succeeded += 1
            except Exception as e:
                console.print(f"  [red]Error:[/red] {e}")
                failed += 1

            if i < len(products):
                import time as _time
                _time.sleep(delay)

    console.print(
        f"\n[bold]Done.[/bold] "
        f"[green]{succeeded} succeeded[/green], "
        f"[red]{failed} failed[/red] "
        f"out of {len(products)} products"
    )


@app.command()
def options() -> None:
    """Show available options, sort modes, and configuration."""
    from ...core.display import display_options
    from .scrapers.search import SORT_OPTIONS

    # Search sort options
    sort_rows = [{"key": k, "value": v} for k, v in SORT_OPTIONS.items()]
    display_options(
        items=sort_rows,
        columns=[
            ColumnDef("Sort Key", "key", style="cyan"),
            ColumnDef("API Value", "value"),
        ],
        title="Search Sort Options",
    )

    console.print()

    # Stock states
    rows = [{"code": k, "label": v} for k, v in STOCK_STATE.items()]
    display_options(
        items=rows,
        columns=[
            ColumnDef("Code", "code", style="cyan"),
            ColumnDef("Label", "label"),
        ],
        title="Stock State Codes",
    )

    console.print()

    # Important cookies
    cookie_rows = [
        {"name": name, "type": "Auth"} for name in AUTH_COOKIES
    ] + [
        {"name": name, "type": "Device/Risk"} for name in DEVICE_COOKIES
    ]
    display_options(
        items=cookie_rows,
        columns=[
            ColumnDef("Cookie", "name", style="cyan"),
            ColumnDef("Type", "type", style="magenta"),
        ],
        title="Important Cookies",
    )

    console.print()
    console.print("[bold]Usage:[/bold]")
    console.print("  scraper jd import-cookies <cookies.txt>")
    console.print("  scraper jd status")
    console.print("  scraper jd search '关键词' -n 30 --sort sales")
    console.print("  scraper jd search '关键词' --price 100-500 --jd-delivery")
    console.print("  scraper jd fetch <url_or_sku_id>")
    console.print("  scraper jd fetch <url> --recommendations --graphic")


if __name__ == "__main__":
    app()
