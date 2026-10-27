"""Plain data containers shared by all modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Quote:
    symbol: str
    price: float
    prev_close: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    volume: Optional[int] = None
    market_state: Optional[str] = None  # e.g. REGULAR / PRE / POST / CLOSED
    # True when the price is the last close rather than a live price.
    is_last_close: bool = False
    currency: str = "USD"

    @property
    def change(self) -> Optional[float]:
        if self.prev_close is None:
            return None
        return self.price - self.prev_close

    @property
    def change_pct(self) -> Optional[float]:
        if not self.prev_close:
            return None
        return (self.price - self.prev_close) / self.prev_close * 100.0


@dataclass
class QuoteResult:
    """Outcome for one symbol: either a quote or an error message."""

    symbol: str
    quote: Optional[Quote] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.quote is not None


@dataclass
class AlertRule:
    """Alert thresholds for one ticker. All fields are optional.

    above / below:      trigger when price >= above / price <= below
    pct_above / pct_below: trigger when day change % >= pct_above / <= pct_below
                           (use a negative number for pct_below, e.g. -3)
    """

    symbol: str
    above: Optional[float] = None
    below: Optional[float] = None
    pct_above: Optional[float] = None
    pct_below: Optional[float] = None

    def is_empty(self) -> bool:
        return all(
            v is None for v in (self.above, self.below, self.pct_above, self.pct_below)
        )


@dataclass
class Watchlist:
    rules: list[AlertRule] = field(default_factory=list)
    interval: Optional[float] = None

    @property
    def symbols(self) -> list[str]:
        return [r.symbol for r in self.rules]

    def rule_for(self, symbol: str) -> AlertRule:
        for r in self.rules:
            if r.symbol == symbol:
                return r
        r = AlertRule(symbol)
        self.rules.append(r)
        return r
