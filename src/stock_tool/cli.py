"""Command line entry point: `stock-tool quote ...` / `stock-tool watch ...`."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from typing import Optional, Sequence

from rich.console import Console

from . import __version__
from .alerts import AlertEngine
from .config import ConfigError, build_watchlist
from .display import build_table
from .notify import bell, desktop_notify
from .sources import DataSource, YFinanceSource

DEFAULT_INTERVAL = 60.0


def make_source() -> DataSource:
    """Factory for the data source; tests monkeypatch this."""
    return YFinanceSource()


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("tickers", nargs="*", help="股票代码,如 AAPL MSFT")
    p.add_argument("-c", "--config", help="watchlist 配置文件 (yaml/toml);未指定时自动查找当前目录的 watchlist.yaml/.toml")
    p.add_argument(
        "-a", "--alert", action="append", default=[], metavar="SPEC",
        help="告警,可重复。例: AAPL>200  AAPL<150  AAPL%%>3  AAPL%%<-3",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stock-tool", description="美股盯盘工具 (数据: Yahoo Finance via yfinance)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    q = sub.add_parser("quote", help="一次性查询报价")
    _add_common(q)

    w = sub.add_parser("watch", help="循环刷新并在触发条件时提醒")
    _add_common(w)
    w.add_argument("-i", "--interval", type=float, help=f"刷新间隔(秒),默认取配置文件或 {DEFAULT_INTERVAL:g}")
    w.add_argument("--no-bell", action="store_true", help="告警时不响终端铃声")
    w.add_argument("--notify", action="store_true", help="告警时发送桌面通知 (notify-send / osascript)")
    w.add_argument("--max-iterations", type=int, default=None, help=argparse.SUPPRESS)
    return p


def cmd_quote(args, console: Console) -> int:
    wl = build_watchlist(args.config, args.tickers, args.alert)
    if not wl.symbols:
        console.print("[red]没有股票代码。[/red] 用法: stock-tool quote AAPL MSFT")
        return 2
    results = make_source().get_quotes(wl.symbols)
    console.print(build_table(results))
    return 0 if any(r.ok for r in results) else 1


def cmd_watch(args, console: Console) -> int:
    wl = build_watchlist(args.config, args.tickers, args.alert)
    if not wl.symbols:
        console.print("[red]没有股票代码。[/red] 用法: stock-tool watch AAPL -a 'AAPL>200'")
        return 2
    interval = args.interval if args.interval is not None else (wl.interval or DEFAULT_INTERVAL)
    if interval < 5:
        console.print("[yellow]间隔过短容易被 Yahoo 限流,已调整为 5 秒。[/yellow]")
        interval = 5.0
    source = make_source()
    engine = AlertEngine(wl.rules)
    n_alerts = sum(0 if r.is_empty() else 1 for r in wl.rules)
    console.print(f"监控 {len(wl.symbols)} 只股票,{n_alerts} 只设置了告警,每 {interval:g} 秒刷新。Ctrl-C 退出。")
    i = 0
    try:
        while True:
            i += 1
            results = source.get_quotes(wl.symbols)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            console.print(build_table(results, title=f"US Stocks @ {now}"))
            for r in results:
                if not r.ok:
                    continue
                for ev in engine.check(r.quote):
                    console.print(f"[bold yellow]🔔 {ev.message()}[/bold yellow]")
                    if not args.no_bell:
                        bell()
                    if args.notify:
                        desktop_notify("stock-tool 告警", ev.message())
            if args.max_iterations is not None and i >= args.max_iterations:
                return 0
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n已退出。")
        return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()
    try:
        if args.command == "quote":
            return cmd_quote(args, console)
        return cmd_watch(args, console)
    except ConfigError as e:
        console.print(f"[red]配置错误:[/red] {e}", highlight=False)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
