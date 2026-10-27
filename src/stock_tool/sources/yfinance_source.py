"""Yahoo Finance via the open-source `yfinance` library (unofficial, no API key)."""
from __future__ import annotations

import logging
import math
import warnings
from typing import Any, Optional

from ..models import Quote
from .base import DataSource, InvalidTickerError, SourceError

logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


class YFinanceSource(DataSource):
    name = "yfinance"

    def __init__(self, ticker_factory=None, with_market_state: bool = True):
        if ticker_factory is None:
            import yfinance as yf

            ticker_factory = yf.Ticker
        self._factory = ticker_factory
        self._with_market_state = with_market_state

    def get_quote(self, symbol: str) -> Quote:
        # yfinance + newest pandas emit deprecation warnings that users cannot act on.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self._get_quote(symbol)

    def _get_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper().strip()
        try:
            t = self._factory(symbol)
            hist = t.history(period="5d", interval="1d", auto_adjust=False)
        except Exception as e:  # yfinance raises many different types
            raise SourceError(f"{symbol}: {type(e).__name__}: {e}") from e

        if hist is None or len(hist) == 0:
            raise InvalidTickerError("没有行情数据,代码可能无效,或网络/Yahoo 不可用")

        closes = [c for c in (_num(x) for x in hist["Close"]) if c is not None]
        if not closes:
            raise InvalidTickerError("没有有效收盘价")
        last_row = hist.iloc[-1]

        price = closes[-1]
        prev_close = closes[-2] if len(closes) >= 2 else None
        day_high = _num(last_row.get("High"))
        day_low = _num(last_row.get("Low"))
        vol = _num(last_row.get("Volume"))

        # fast_info has a fresher price while the market is open.
        live = False
        try:
            fi = t.fast_info
            lp = _num(fi["last_price"])
            pc = _num(fi["previous_close"])
            if lp is not None:
                price = lp
                live = True
            if pc is not None:
                prev_close = pc
            day_high = _num(fi["day_high"]) or day_high
            day_low = _num(fi["day_low"]) or day_low
        except Exception:  # noqa: BLE001 - fall back to history values
            pass

        state = None
        if self._with_market_state:
            try:
                state = t.get_info().get("marketState")
            except Exception:  # noqa: BLE001 - optional field
                state = None

        closed = state is not None and state.upper() in {"CLOSED", "POSTPOST", "PREPRE"}
        return Quote(
            symbol=symbol,
            price=price,
            prev_close=prev_close,
            day_high=day_high,
            day_low=day_low,
            volume=int(vol) if vol is not None else None,
            market_state=state,
            is_last_close=closed or (state is None and not live),
        )
