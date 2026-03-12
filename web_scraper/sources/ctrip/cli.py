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
    help="携程 Ctrip 命令。",
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
    keyword: str = typer.Option("", "--keyword", "-k", help="关键词搜索，如 地铁旁、亲子"),
    brand: str = typer.Option("", "--brand", "-b",
                              help="品牌筛选，多个用逗号分隔，如 亚朵,全季。运行 options 查看支持的品牌"),
    no_save: bool = typer.Option(False, "--no-save", help="不保存结果文件"),
) -> None:
    """搜索酒店（Playwright 拦截 XHR，无需登录）。"""
    from .scrapers import HotelSearchScraper

    stars = [int(s.strip()) for s in star.split(",") if s.strip().isdigit()] if star else None
    brands = [b.strip() for b in brand.split(",") if b.strip()] if brand else None

    scraper = HotelSearchScraper()
    try:
        with console.status(f"搜索 {city} 酒店 {checkin} → {checkout}（启动浏览器…）"):
            result = scraper.search(
                city, checkin, checkout,
                adult=adult, rooms=rooms, limit=limit,
                sort=sort, stars=stars,
                breakfast=breakfast, free_cancel=free_cancel,
                price_min=price_min, price_max=price_max,
                keyword=keyword, brands=brands,
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
# Hotel: fetch (detail)
# ─────────────────────────────────────────

@app.command()
def fetch(
    hotel_id: str = typer.Argument(..., help="酒店 ID"),
    city: str = typer.Option(..., "--city", "-c", help="城市名，如 上海"),
    checkin: str = typer.Option(..., "--checkin", "-i", help="入住日期 YYYY-MM-DD"),
    checkout: str = typer.Option(..., "--checkout", "-o", help="退房日期 YYYY-MM-DD"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="是否无头浏览器"),
    no_save: bool = typer.Option(False, "--no-save", help="不保存结果文件"),
) -> None:
    """获取酒店详情页信息（Playwright DOM 解析）。"""
    from .config import CITY_MAP
    from .scrapers import HotelDetailScraper

    city_info = CITY_MAP.get(city)
    if city_info is None:
        console.print(f"[red]不支持的城市：{city}[/red]")
        raise typer.Exit(1)

    city_id = city_info[0]
    scraper = HotelDetailScraper(headless=headless)
    try:
        with console.status(f"获取酒店 {hotel_id} 详情…"):
            detail = scraper.fetch(hotel_id, city_id, checkin, checkout)
    except Exception as e:
        console.print(f"[red]获取详情失败：{e}[/red]")
        raise typer.Exit(1)

    _display_hotel_detail(detail)
    if not no_save:
        _save_hotel_detail(detail)


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
    """显示可用命令、筛选选项和会员等级说明。"""
    from .config import BRAND_FILTERS, FLIGHT_CITY_CODE_MAP, GRADE_MAP

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
        ("fetch <酒店ID> --city 城市 --checkin DATE --checkout DATE", "获取酒店详情（Playwright DOM 解析）"),
        ("recommend <城市> --checkin DATE --checkout DATE", "获取推荐酒店（API，无需浏览器）"),
        ("history --checkin DATE --checkout DATE", "最近浏览过的酒店（需登录）"),
        ("cities", "列出可搜索的城市"),
    ]
    for cmd, desc in hotel_cmds:
        console.print(f"  [cyan]scraper ctrip {cmd}[/cyan]  {desc}")

    console.print("\n[bold]酒店搜索筛选[/bold]")
    console.print("  [dim]--sort[/dim]  排序：popular / smart / score / price_asc / price_desc / distance / star")
    console.print("  [dim]--star[/dim]  星级：2,3,4,5（逗号分隔）")
    console.print("  [dim]--breakfast[/dim]  只看含早餐")
    console.print("  [dim]--free-cancel[/dim]  只看免费取消")
    console.print("  [dim]--price-min / --price-max[/dim]  价格区间（元）")
    console.print("  [dim]--keyword[/dim]  关键词，如 地铁旁、亲子、江景")
    console.print("  [dim]--brand[/dim]  品牌（逗号分隔）：")
    brand_names = list(BRAND_FILTERS.keys())
    # Show in rows of 6
    for i in range(0, len(brand_names), 6):
        console.print(f"    {' / '.join(brand_names[i:i+6])}")

    console.print("\n[bold]机票命令[/bold]")
    flight_cmds = [
        ("flight-search <出发地> <目的地> --date DATE", "搜索机票结果页并抓取航班列表"),
        ("flight-calendar <出发地> <目的地> --date DATE", "获取未来一段时间低价日历"),
        ("flight-cities", "列出内置机票城市与三字码"),
    ]
    for cmd, desc in flight_cmds:
        console.print(f"  [cyan]scraper ctrip {cmd}[/cyan]  {desc}")

    console.print("\n[bold]会员等级[/bold]")
    t = Table(box=box.SIMPLE)
    t.add_column("编号", style="dim")
    t.add_column("名称")
    for k, v in GRADE_MAP.items():
        t.add_row(k, v)
    console.print(t)

    console.print(f"\n[dim]当前内置机票城市数：{len(FLIGHT_CITY_CODE_MAP)}[/dim]")


@app.command("flight-search")
def flight_search(
    departure: str = typer.Argument(..., help="出发城市或三字码，如 上海 / SHA"),
    arrival: str = typer.Argument(..., help="到达城市或三字码，如 北京 / BJS"),
    date: str = typer.Option(..., "--date", "-d", help="出发日期 YYYY-MM-DD"),
    limit: int = typer.Option(20, "-n", "--limit", help="最多返回条数"),
    direct_only: bool = typer.Option(False, "--direct-only", help="只保留直飞航班"),
    no_calendar: bool = typer.Option(False, "--no-calendar", help="不查询低价日历"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="是否无头浏览器运行"),
    no_save: bool = typer.Option(False, "--no-save", help="不保存结果文件"),
) -> None:
    """搜索机票结果页并解析航班列表。"""
    from .scrapers import FlightSearchScraper

    scraper = FlightSearchScraper(headless=headless)
    try:
        with console.status(f"搜索 {departure} → {arrival} 机票（{date}）…"):
            result = scraper.search(
                departure_city=departure,
                arrival_city=arrival,
                departure_date=date,
                limit=limit,
                direct_only=direct_only,
                with_calendar=not no_calendar,
            )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]机票搜索失败：{e}[/red]")
        raise typer.Exit(1)

    if result.calendar_prices:
        _display_flight_calendar(result.calendar_prices[:7], title="近期开票低价")

    if not result.flights:
        message = result.no_result_message or "未找到符合条件的航班"
        console.print(f"[yellow]{message}[/yellow]")
        console.print(f"[dim]{result.search_url}[/dim]")
        return

    _display_flights(
        result.flights,
        title=f"{result.departure_city} → {result.arrival_city}（{result.departure_date}）",
    )
    console.print(f"[dim]结果页：{result.search_url}[/dim]")

    if not no_save:
        _save_flights(
            result.model_dump(),
            f"flight_search_{result.departure_code}_{result.arrival_code}_{result.departure_date}",
        )


@app.command("flight-calendar")
def flight_calendar(
    departure: str = typer.Argument(..., help="出发城市或三字码，如 上海 / SHA"),
    arrival: str = typer.Argument(..., help="到达城市或三字码，如 北京 / BJS"),
    date: str = typer.Option(..., "--date", "-d", help="基准日期 YYYY-MM-DD"),
    days: int = typer.Option(30, "--days", help="展示未来多少天，默认 30"),
    no_save: bool = typer.Option(False, "--no-save", help="不保存结果文件"),
) -> None:
    """查询机票低价日历。"""
    from .config import normalize_flight_city
    from .scrapers import FlightLowPriceScraper

    try:
        dep_code, dep_name = normalize_flight_city(departure)
        arr_code, arr_name = normalize_flight_city(arrival)
        scraper = FlightLowPriceScraper()
        with console.status(f"获取 {dep_name} → {arr_name} 低价日历…"):
            prices = scraper.search(dep_code, arr_code, date)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]获取低价日历失败：{e}[/red]")
        raise typer.Exit(1)

    if not prices:
        console.print("[yellow]暂无低价日历数据[/yellow]")
        return

    shown_prices = prices[:days] if days > 0 else prices
    _display_flight_calendar(shown_prices, title=f"{dep_name} → {arr_name} 低价日历")
    if not no_save:
        _save_flights(
            {
                "departure_city": dep_name,
                "departure_code": dep_code,
                "arrival_city": arr_name,
                "arrival_code": arr_code,
                "departure_date": date,
                "days": days,
                "calendar_prices": [item.model_dump() for item in prices],
            },
            f"flight_calendar_{dep_code}_{arr_code}_{date}",
        )


@app.command("flight-cities")
def flight_cities() -> None:
    """列出内置机票城市与三字码。"""
    from .config import FLIGHT_CITY_CODE_MAP

    table = Table(title=f"机票城市（{len(FLIGHT_CITY_CODE_MAP)} 个）", box=box.ROUNDED)
    table.add_column("城市名", style="cyan")
    table.add_column("三字码", justify="center", style="yellow")

    for name, code in FLIGHT_CITY_CODE_MAP.items():
        table.add_row(name, code)
    console.print(table)


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

    data_dir = get_data_dir(SOURCE_NAME) / "exports"
    data_dir.mkdir(parents=True, exist_ok=True)
    out = data_dir / f"{filename_prefix}.json"
    out.write_text(
        json.dumps([h.model_dump() for h in hotels], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    console.print(f"[dim]已保存至 {out}[/dim]")


def _display_hotel_detail(detail) -> None:
    """Display hotel detail as Rich panels."""
    # Basic info table
    table = Table(title=detail.name, box=box.ROUNDED, show_header=False)
    table.add_column("字段", style="dim", width=12)
    table.add_column("值", style="cyan")

    STAR_ICONS = {5: "★★★★★", 4: "★★★★", 3: "★★★", 2: "★★"}
    if detail.star:
        table.add_row("星级", STAR_ICONS.get(detail.star, f"{detail.star}星"))
    if detail.score:
        score_text = detail.score
        if detail.score_desc:
            score_text += f" {detail.score_desc}"
        if detail.comment_count:
            score_text += f"（{detail.comment_count}）"
        table.add_row("评分", score_text)
    if detail.address:
        table.add_row("地址", detail.address)
    if detail.phone:
        table.add_row("电话", detail.phone)
    if detail.opening_year:
        table.add_row("开业", detail.opening_year)
    if detail.renovation_year:
        table.add_row("装修", detail.renovation_year)
    if detail.room_count:
        table.add_row("客房数", str(detail.room_count))
    if detail.tags:
        table.add_row("标签", " | ".join(detail.tags))
    if detail.facilities:
        table.add_row("设施", " | ".join(detail.facilities[:15]))
    if detail.name_en:
        table.add_row("英文名", detail.name_en)

    console.print(table)

    # Rooms
    if detail.rooms:
        rt = Table(title=f"房型（{len(detail.rooms)} 种）", box=box.ROUNDED)
        rt.add_column("房型", style="cyan", max_width=20)
        rt.add_column("床型", width=10)
        rt.add_column("早餐", width=10)
        rt.add_column("价格", justify="right", style="green", width=10)
        rt.add_column("取消政策", max_width=14)
        rt.add_column("标签", max_width=18)

        for r in detail.rooms:
            rt.add_row(
                r.room_name,
                r.bed_type or "",
                r.breakfast or "",
                r.price or "",
                r.cancel_policy or "",
                " ".join(r.tags[:3]),
            )
        console.print(rt)

    console.print(f"[dim]{detail.detail_url}[/dim]")


def _save_hotel_detail(detail) -> None:
    """Save hotel detail as JSON."""
    import json
    data_dir = get_data_dir(SOURCE_NAME) / "exports"
    data_dir.mkdir(parents=True, exist_ok=True)
    out = data_dir / f"hotel_detail_{detail.hotel_id}.json"
    out.write_text(
        json.dumps(detail.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    console.print(f"[dim]已保存至 {out}[/dim]")


def _display_flights(flights, title: str) -> None:
    """Display flight cards as a Rich table."""
    table = Table(title=f"{title}（{len(flights)} 班）", box=box.ROUNDED)
    table.add_column("航司/航班", style="cyan", max_width=22)
    table.add_column("起飞", justify="center", width=7)
    table.add_column("到达", justify="center", width=7)
    table.add_column("机场", max_width=24, style="dim")
    table.add_column("中转", max_width=14)
    table.add_column("价格", justify="right", style="green", width=8)
    table.add_column("舱位", max_width=14)
    table.add_column("标签", max_width=18)

    for flight in flights:
        airline_text = " / ".join(flight.airlines[:2]) or "-"
        if flight.flight_numbers:
            airline_text = f"{airline_text}\n{' / '.join(flight.flight_numbers[:2])}"
        airport_text = (
            f"{flight.departure_airport}{flight.departure_terminal or ''}\n"
            f"{flight.arrival_airport}{flight.arrival_terminal or ''}"
        )
        transfer_text = "直飞" if flight.is_direct else (flight.transfer_duration or f"转{flight.transfer_count}次")
        if flight.transfer_description:
            transfer_text = f"{transfer_text}\n{flight.transfer_description}"
        tags = " ".join(flight.tags[:3]) if flight.tags else ""
        table.add_row(
            airline_text,
            flight.departure_time,
            flight.arrival_time,
            airport_text,
            transfer_text,
            flight.price or "",
            " / ".join(flight.cabin_classes[:2]),
            tags,
        )
    console.print(table)


def _display_flight_calendar(prices, title: str) -> None:
    """Display low-price calendar as a Rich table."""
    table = Table(title=title, box=box.SIMPLE)
    table.add_column("日期", style="cyan")
    table.add_column("票面价", justify="right", style="green")
    table.add_column("总价", justify="right", style="yellow")
    table.add_column("标签")

    for item in prices:
        labels = " ".join(v for v in [item.discount_label, item.direct_label] if v)
        table.add_row(
            item.date,
            f"{item.price:.0f}" if item.price is not None else "-",
            f"{item.total_price:.0f}" if item.total_price is not None else "-",
            labels,
        )
    console.print(table)


def _save_flights(payload, filename_prefix: str) -> None:
    """Save generic flight payload as JSON."""
    import json

    data_dir = get_data_dir(SOURCE_NAME) / "exports"
    data_dir.mkdir(parents=True, exist_ok=True)
    out = data_dir / f"{filename_prefix}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"[dim]已保存至 {out}[/dim]")
