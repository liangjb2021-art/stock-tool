"""Rich table rendering."""
from __future__ import annotations

from typing import Optional

from rich.table import Table

from .models import QuoteResult

_STATE_ZH = {
    "REGULAR": "盘中",
    "PRE": "盘前",
    "PREPRE": "盘前(未开)",
    "POST": "盘后",
    "POSTPOST": "盘后(已收)",
    "CLOSED": "已收盘",
}


def _f(v: Optional[float], nd: int = 2) -> str:
    return "-" if v is None else f"{v:,.{nd}f}"


def _vol(v: Optional[int]) -> str:
    return "-" if v is None else f"{v:,}"


def _color(v: Optional[float]) -> str:
    if v is None or v == 0:
        return "white"
    return "green" if v > 0 else "red"  # US convention: green up, red down


def build_table(results: list[QuoteResult], title: str = "US Stocks") -> Table:
    t = Table(title=title, caption_justify="left")
    t.add_column("代码", style="bold cyan", no_wrap=True)
    t.add_column("最新价", justify="right")
    t.add_column("涨跌", justify="right")
    t.add_column("涨跌幅", justify="right")
    t.add_column("最高", justify="right")
    t.add_column("最低", justify="right")
    t.add_column("成交量", justify="right", no_wrap=True)
    t.add_column("市场状态", no_wrap=True)
    for r in results:
        if not r.ok:
            t.add_row(r.symbol, "[red]错误[/red]", "-", "-", "-", "-", "-", "-")
            continue
        q = r.quote
        c = _color(q.change)
        chg = "-" if q.change is None else f"[{c}]{q.change:+,.2f}[/{c}]"
        pct = "-" if q.change_pct is None else f"[{c}]{q.change_pct:+.2f}%[/{c}]"
        state = _STATE_ZH.get(q.market_state or "", q.market_state or "-")
        sym = q.symbol + ("*" if q.is_last_close else "")
        t.add_row(sym, _f(q.price), chg, pct, _f(q.day_high), _f(q.day_low), _vol(q.volume), state)
    notes = [f"{r.symbol}: {r.error}" for r in results if not r.ok]
    if any(r.ok and r.quote.is_last_close for r in results):
        notes.append("* 当前非交易时段,价格为最近收盘价")
    if notes:
        t.caption = "\n".join(notes)
    return t
