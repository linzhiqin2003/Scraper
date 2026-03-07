"""CLI commands for Ctrip."""
import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from ...core.browser import get_data_dir
from .config import SOURCE_NAME
from .cookies import (
    get_cookies_path,
    load_cookies,
    validate_cookies,
    check_cookies_valid,
    get_username_from_cookie,
)

app = typer.Typer(
    name=SOURCE_NAME,
    help="携程 Ctrip 用户中心命令。",
    no_args_is_help=True,
)
console = Console()


# ─────────────────────────────────────────
# login
# ─────────────────────────────────────────

@app.command()
def login(
    timeout: int = typer.Option(180, "-t", "--timeout", help="等待登录的超时秒数"),
) -> None:
    """打开浏览器，等待用户完成登录（扫码/验证码/账密均可）。"""
    from .auth import interactive_login, LoginStatus

    result = interactive_login(timeout_seconds=timeout)

    if result.status == LoginStatus.LOGGED_IN:
        console.print(f"[green]✓ {result.message}[/green]")
        console.print("[dim]运行 'scraper ctrip status' 验证接口连通性[/dim]")
    else:
        console.print(f"[red]✗ {result.message}[/red]")
        raise typer.Exit(1)


# ─────────────────────────────────────────
# import-cookies
# ─────────────────────────────────────────

@app.command("import-cookies")
def import_cookies(
    cookies_file: str = typer.Argument(..., help="Netscape 格式 cookies.txt 文件路径"),
) -> None:
    """从浏览器插件导出的 cookies 文件导入登录状态。"""
    src = Path(cookies_file).expanduser()
    if not src.exists():
        console.print(f"[red]文件不存在：{src}[/red]")
        raise typer.Exit(1)

    dest = get_cookies_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    console.print(f"[green]✓ Cookies 已导入：{dest}[/green]")

    # 快速验证
    try:
        cookies = load_cookies(dest)
        if validate_cookies(cookies):
            username = get_username_from_cookie(cookies)
            hint = f"（{username}）" if username else ""
            console.print(f"[green]✓ 认证 Cookie 有效{hint}[/green]")
            console.print("[dim]运行 'scraper ctrip status' 验证接口连通性[/dim]")
        else:
            console.print("[yellow]⚠ 未找到完整认证 Cookie，请确认已登录后重新导出[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠ Cookie 解析警告：{e}[/yellow]")


# ─────────────────────────────────────────
# status
# ─────────────────────────────────────────

@app.command()
def status() -> None:
    """检查登录状态（调用用户信息接口验证）。"""
    path = get_cookies_path()
    if not path.exists():
        console.print("[yellow]未找到 cookies 文件[/yellow]")
        console.print(f"[dim]请运行：scraper ctrip import-cookies <文件路径>[/dim]")
        raise typer.Exit(1)

    try:
        cookies = load_cookies(path)
    except Exception as e:
        console.print(f"[red]读取 cookies 失败：{e}[/red]")
        raise typer.Exit(1)

    if not validate_cookies(cookies):
        console.print("[red]✗ 认证 Cookie 不完整，请重新导出[/red]")
        raise typer.Exit(1)

    console.print("[dim]正在验证登录状态…[/dim]")
    ok, msg = check_cookies_valid(cookies)
    if ok:
        console.print(f"[green]✓ {msg}[/green]")
    else:
        console.print(f"[red]✗ {msg}[/red]")
        raise typer.Exit(1)


# ─────────────────────────────────────────
# logout
# ─────────────────────────────────────────

@app.command()
def logout() -> None:
    """清除本地保存的 cookies（本地退出，不影响网页端登录状态）。"""
    from .auth import clear_session

    if clear_session():
        console.print("[green]✓ 已清除本地 cookies[/green]")
    else:
        console.print("[yellow]未找到 cookies 文件，无需清除[/yellow]")


# ─────────────────────────────────────────
# profile
# ─────────────────────────────────────────

@app.command()
def profile() -> None:
    """显示登录用户的会员信息。"""
    from .scrapers import UserCenterScraper

    scraper = _get_scraper()
    if scraper is None:
        raise typer.Exit(1)

    try:
        with console.status("获取用户信息…"):
            p = scraper.get_profile()
    except Exception as e:
        console.print(f"[red]请求失败：{e}[/red]")
        raise typer.Exit(1)

    table = Table(title="会员信息", box=box.ROUNDED, show_header=False)
    table.add_column("字段", style="dim", width=12)
    table.add_column("值", style="cyan")

    table.add_row("昵称", p.user_name)
    table.add_row("会员等级", f"{p.grade_name}（{p.grade}）")
    table.add_row("超级会员", "是" if p.svip else "否")
    table.add_row("企业账户", "是" if p.is_corp else "否")
    if p.avatar_url:
        table.add_row("头像", p.avatar_url)

    if p.assets:
        table.add_row("─── 资产 ───", "")
        for a in p.assets:
            table.add_row(a.asset_type, str(int(a.balance)))

    console.print(table)


# ─────────────────────────────────────────
# points
# ─────────────────────────────────────────

@app.command()
def points() -> None:
    """查看携程积分余额。"""
    scraper = _get_scraper()
    if scraper is None:
        raise typer.Exit(1)

    try:
        with console.status("获取积分信息…"):
            pts = scraper.get_points()
    except Exception as e:
        console.print(f"[red]请求失败：{e}[/red]")
        raise typer.Exit(1)

    table = Table(title="积分余额", box=box.ROUNDED, show_header=False)
    table.add_column("类型", style="dim", width=14)
    table.add_column("积分", style="yellow", justify="right")

    table.add_row("可用积分", f"{pts.total_available:,}")
    table.add_row("总余额（含冻结）", f"{pts.total_balance:,}")
    table.add_row("待入账", f"{pts.total_pending:,}")
    if pts.is_freeze:
        table.add_row("账户状态", "[red]已冻结[/red]")

    console.print(table)


# ─────────────────────────────────────────
# messages
# ─────────────────────────────────────────

@app.command()
def messages() -> None:
    """查看未读消息数量。"""
    scraper = _get_scraper()
    if scraper is None:
        raise typer.Exit(1)

    try:
        with console.status("获取消息统计…"):
            msg = scraper.get_messages()
    except Exception as e:
        console.print(f"[red]请求失败：{e}[/red]")
        raise typer.Exit(1)

    total = msg.total_unread
    if total == 0:
        console.print("[green]✓ 暂无未读消息[/green]")
        return

    table = Table(title=f"未读消息（共 {total} 条）", box=box.ROUNDED)
    table.add_column("类型", style="cyan")
    table.add_column("状态")
    table.add_column("数量", justify="right", style="yellow")
    table.add_column("提醒")

    for s in msg.stats:
        table.add_row(
            s.msg_type,
            s.status,
            str(s.count),
            "是" if s.need_prompt else "否",
        )

    console.print(table)


# ─────────────────────────────────────────
# Hotel: search
# ─────────────────────────────────────────

@app.command()
def search(
    city: str = typer.Argument(..., help="城市名，如 上海、北京、三亚"),
    checkin: str = typer.Option(..., "--checkin", "-i", help="入住日期 YYYY-MM-DD"),
    checkout: str = typer.Option(..., "--checkout", "-o", help="退房日期 YYYY-MM-DD"),
    adult: int = typer.Option(1, "--adult", "-a", help="成人数"),
    rooms: int = typer.Option(1, "--rooms", "-r", help="房间数"),
    limit: int = typer.Option(20, "-n", "--limit", help="最多返回条数"),
    sort: str = typer.Option("popular", "--sort", "-s",
                             help="排序：popular/smart/score/price_asc/price_desc/distance/star"),
    star: str = typer.Option("", "--star", help="星级筛选，多个用逗号分隔，如 4,5"),
    breakfast: bool = typer.Option(False, "--breakfast", help="只看含早餐"),
    free_cancel: bool = typer.Option(False, "--free-cancel", help="只看免费取消"),
    price_min: int = typer.Option(None, "--price-min", help="最低价格（元）"),
    price_max: int = typer.Option(None, "--price-max", help="最高价格（元）"),
    no_save: bool = typer.Option(False, "--no-save", help="不保存结果文件"),
) -> None:
    """搜索酒店（Playwright 拦截 XHR，无需登录）。"""
    from .scrapers import HotelSearchScraper

    stars = [int(s.strip()) for s in star.split(",") if s.strip().isdigit()] if star else None

    scraper = HotelSearchScraper()
    try:
        with console.status(f"搜索 {city} 酒店 {checkin} → {checkout}（启动浏览器…）"):
            result = scraper.search(
                city, checkin, checkout,
                adult=adult, rooms=rooms, limit=limit,
                sort=sort, stars=stars,
                breakfast=breakfast, free_cancel=free_cancel,
                price_min=price_min, price_max=price_max,
            )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]搜索失败：{e}[/red]")
        raise typer.Exit(1)

    if not result.hotels:
        console.print("[yellow]未找到酒店，请检查城市名称或日期[/yellow]")
        return

    _display_hotels(result.hotels, title=f"{city} 酒店搜索结果（{checkin} → {checkout}）")

    if not no_save:
        _save_hotels(result.hotels, f"hotel_search_{city}_{checkin}")


# ─────────────────────────────────────────
# Hotel: recommend
# ─────────────────────────────────────────

@app.command()
def recommend(
    city: str = typer.Argument(..., help="城市名，如 上海、北京"),
    checkin: str = typer.Option(..., "--checkin", "-i", help="入住日期 YYYY-MM-DD"),
    checkout: str = typer.Option(..., "--checkout", "-o", help="退房日期 YYYY-MM-DD"),
    no_save: bool = typer.Option(False, "--no-save", help="不保存结果文件"),
) -> None:
    """获取酒店广告推荐（API 直连，无需 Playwright）。"""
    from .config import CITY_MAP
    from .scrapers import HotelApiScraper

    city_info = CITY_MAP.get(city)
    if city_info is None:
        console.print(f"[red]不支持的城市：{city}。运行 'scraper ctrip cities' 查看列表[/red]")
        raise typer.Exit(1)

    city_id = city_info[0]
    scraper = _get_hotel_api_scraper()
    if scraper is None:
        raise typer.Exit(1)

    try:
        with console.status(f"获取 {city} 推荐酒店…"):
            hotels = scraper.get_recommendations(city_id, checkin, checkout)
    except Exception as e:
        console.print(f"[red]请求失败：{e}[/red]")
        raise typer.Exit(1)

    if not hotels:
        console.print("[yellow]暂无推荐酒店[/yellow]")
        return

    _display_hotels(hotels, title=f"{city} 推荐酒店（{checkin} → {checkout}）")
    if not no_save:
        _save_hotels(hotels, f"hotel_recommend_{city}_{checkin}")


# ─────────────────────────────────────────
# Hotel: history
# ─────────────────────────────────────────

@app.command()
def history(
    checkin: str = typer.Option(..., "--checkin", "-i", help="入住日期 YYYY-MM-DD"),
    checkout: str = typer.Option(..., "--checkout", "-o", help="退房日期 YYYY-MM-DD"),
) -> None:
    """查看最近浏览过的酒店（需要登录）。"""
    scraper = _get_hotel_api_scraper()
    if scraper is None:
        raise typer.Exit(1)

    try:
        with console.status("获取浏览历史…"):
            hotels = scraper.get_browse_history(checkin, checkout)
    except Exception as e:
        console.print(f"[red]请求失败：{e}[/red]")
        raise typer.Exit(1)

    if not hotels:
        console.print("[yellow]暂无浏览记录[/yellow]")
        return

    _display_hotels(hotels, title=f"最近浏览酒店（{checkin} → {checkout}）")


# ─────────────────────────────────────────
# Hotel: cities
# ─────────────────────────────────────────

@app.command()
def cities(
    checkin: str = typer.Option("", "--checkin", help="入住日期（可选）"),
    checkout: str = typer.Option("", "--checkout", help="退房日期（可选）"),
) -> None:
    """列出可搜索的热门城市及携程城市 ID。"""
    from .config import CITY_MAP

    console.print("\n[bold]内置城市列表[/bold]（可直接用于 search/recommend 命令）\n")
    t = Table(box=box.ROUNDED)
    t.add_column("城市名", style="cyan")
    t.add_column("城市 ID", justify="right", style="dim")
    t.add_column("英文名")
    for name, (cid, _, en) in CITY_MAP.items():
        t.add_row(name, str(cid), en)
    console.print(t)

    if checkin and checkout:
        # Also fetch from API
        scraper = _get_hotel_api_scraper()
        if scraper:
            try:
                with console.status("从 API 获取完整城市列表…"):
                    api_cities = scraper.get_cities(checkin, checkout)
                if api_cities:
                    console.print(f"\n[dim]API 返回 {len(api_cities)} 个城市（仅显示前 30）[/dim]")
                    t2 = Table(box=box.SIMPLE)
                    t2.add_column("城市名", style="cyan")
                    t2.add_column("城市 ID", justify="right", style="dim")
                    t2.add_column("分组")
                    for c in api_cities[:30]:
                        t2.add_row(c.city_name, str(c.city_id), c.group_name or "")
                    console.print(t2)
            except Exception:
                pass


# ─────────────────────────────────────────
# options
# ─────────────────────────────────────────

@app.command()
def options() -> None:
    """显示可用命令和会员等级说明。"""
    from .config import GRADE_MAP

    console.print("\n[bold]用户中心命令[/bold]")
    user_cmds = [
        ("login", "打开浏览器完成交互式登录"),
        ("import-cookies <文件>", "导入浏览器插件导出的 cookies 文件"),
        ("status", "验证登录状态（调用接口）"),
        ("logout", "清除本地 cookies"),
        ("profile", "查看会员信息"),
        ("points", "查看积分余额"),
        ("messages", "查看未读消息"),
    ]
    for cmd, desc in user_cmds:
        console.print(f"  [cyan]scraper ctrip {cmd}[/cyan]  {desc}")

    console.print("\n[bold]酒店命令[/bold]")
    hotel_cmds = [
        ("search <城市> --checkin DATE --checkout DATE", "搜索酒店（Playwright XHR 拦截，无需登录）"),
        ("recommend <城市> --checkin DATE --checkout DATE", "获取推荐酒店（API，无需浏览器）"),
        ("history --checkin DATE --checkout DATE", "最近浏览过的酒店（需登录）"),
        ("cities", "列出可搜索的城市"),
    ]
    for cmd, desc in hotel_cmds:
        console.print(f"  [cyan]scraper ctrip {cmd}[/cyan]  {desc}")

    console.print("\n[bold]会员等级[/bold]")
    t = Table(box=box.SIMPLE)
    t.add_column("编号", style="dim")
    t.add_column("名称")
    for k, v in GRADE_MAP.items():
        t.add_row(k, v)
    console.print(t)


# ─────────────────────────────────────────
# helpers
# ─────────────────────────────────────────

def _get_scraper():
    """Load cookies and return UserCenterScraper, or print error and return None."""
    from .scrapers import UserCenterScraper

    path = get_cookies_path()
    if not path.exists():
        console.print("[red]未找到 cookies，请先运行：scraper ctrip import-cookies <文件>[/red]")
        return None
    try:
        return UserCenterScraper(cookies_path=path)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return None


def _get_hotel_api_scraper():
    """Load cookies and return HotelApiScraper, or print error and return None."""
    from .scrapers import HotelApiScraper

    path = get_cookies_path()
    if not path.exists():
        console.print("[red]未找到 cookies，请先运行：scraper ctrip import-cookies <文件>[/red]")
        return None
    try:
        return HotelApiScraper(cookies_path=path)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return None


def _display_hotels(hotels, title: str = "酒店列表") -> None:
    """Display hotel list as a Rich table."""
    table = Table(title=f"{title}（{len(hotels)} 家）", box=box.ROUNDED)
    table.add_column("酒店名称", style="cyan", max_width=26)
    table.add_column("星", justify="center", width=4)
    table.add_column("评分", justify="center", style="yellow", width=8)
    table.add_column("地址", max_width=18, style="dim")
    table.add_column("价格", justify="right", style="green", width=9)
    table.add_column("房型", max_width=14, style="dim")
    table.add_column("标签", width=10)

    STAR_ICONS = {5: "★★★★★", 4: "★★★★", 3: "★★★", 2: "★★"}
    for h in hotels:
        score = h.score or ""
        if h.score_desc:
            score = f"{score} {h.score_desc}"
        tags = []
        if h.free_cancel:
            tags.append("[green]免取消[/green]")
        if h.is_ad:
            tags.append("[dim]广告[/dim]")
        if h.promotion:
            tags.append(f"[magenta]{h.promotion[:5]}[/magenta]")

        table.add_row(
            h.name,
            STAR_ICONS.get(h.star, ""),
            score.strip(),
            h.address or "",
            h.price or "",
            h.room_name or "",
            " ".join(tags),
        )
    console.print(table)


def _save_hotels(hotels, filename_prefix: str) -> None:
    """Save hotel list as JSON."""
    import json
    from ...core.browser import get_data_dir

    data_dir = get_data_dir(SOURCE_NAME) / "exports"
    data_dir.mkdir(parents=True, exist_ok=True)
    out = data_dir / f"{filename_prefix}.json"
    out.write_text(
        json.dumps([h.model_dump() for h in hotels], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    console.print(f"[dim]已保存至 {out}[/dim]")
