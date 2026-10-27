"""Edge-triggered alert engine: each alert fires once per crossing."""
from __future__ import annotations

from dataclasses import dataclass

from .models import AlertRule, Quote

LABELS = {
    "above": "价格 ≥ {thr:g}",
    "below": "价格 ≤ {thr:g}",
    "pct_above": "涨跌幅 ≥ {thr:g}%",
    "pct_below": "涨跌幅 ≤ {thr:g}%",
}


@dataclass
class AlertEvent:
    symbol: str
    kind: str
    threshold: float
    price: float
    change_pct: float | None

    def message(self) -> str:
        cond = LABELS[self.kind].format(thr=self.threshold)
        pct = f" ({self.change_pct:+.2f}%)" if self.change_pct is not None else ""
        return f"{self.symbol} 触发告警: {cond},当前价 {self.price:.2f}{pct}"


class AlertEngine:
    """Remembers which conditions are currently true.

    An alert fires on the False -> True transition and is re-armed as soon as the
    condition becomes False again. The first observation that is already true also
    fires (once), so you learn about a condition that holds when you start watching.
    """

    def __init__(self, rules: list[AlertRule]):
        self._rules = {r.symbol: r for r in rules}
        self._active: dict[tuple[str, str], bool] = {}

    @staticmethod
    def _conditions(rule: AlertRule, q: Quote) -> list[tuple[str, float, bool]]:
        out: list[tuple[str, float, bool]] = []
        pct = q.change_pct
        if rule.above is not None:
            out.append(("above", rule.above, q.price >= rule.above))
        if rule.below is not None:
            out.append(("below", rule.below, q.price <= rule.below))
        if rule.pct_above is not None and pct is not None:
            out.append(("pct_above", rule.pct_above, pct >= rule.pct_above))
        if rule.pct_below is not None and pct is not None:
            out.append(("pct_below", rule.pct_below, pct <= rule.pct_below))
        return out

    def check(self, quote: Quote) -> list[AlertEvent]:
        rule = self._rules.get(quote.symbol)
        if rule is None:
            return []
        events: list[AlertEvent] = []
        for kind, thr, hit in self._conditions(rule, quote):
            key = (quote.symbol, kind)
            was = self._active.get(key, False)
            self._active[key] = hit
            if hit and not was:
                events.append(AlertEvent(quote.symbol, kind, thr, quote.price, quote.change_pct))
        return events
