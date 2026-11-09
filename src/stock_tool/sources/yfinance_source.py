"""Yahoo Finance via the open-source `yfinance` library (unofficial, no API key)."""
from __future__ import annotations

import logging
import math
import time
import warnings
from typing import Any, Optional

from ..models import Quote, QuoteResult
from .base import DataSource, InvalidTickerError, SourceError

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# Soft retry when Yahoo rate-limits; keep short so CLI stays responsive.
_RATE_LIMIT_RETRIES = 2
_RATE_LIMIT_SLEEP_S = 3.0
_DOWNLOAD_DEFAULT = object()


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _is_rate_limit(exc: BaseException) -> bool:
    name = type(exc).__name__
    if "RateLimit" in name:
        return True
    msg = str(exc).lower()
    return "too many requests" in msg or "rate limited" in msg or "rate limit" in msg


def _rate_limit_error(symbol: str) -> SourceError:
    return SourceError(
        f"{symbol}: Yahoo 限流 (Too Many Requests)。请稍后再试，"
        f"或拉长 watch 间隔（建议 ≥60 秒）"
    )


class YFinanceSource(DataSource):
    name = "yfinance"

    def __init__(
        self,
        ticker_factory=None,
        download_fn=_DOWNLOAD_DEFAULT,
        with_market_state: bool = True,
        rate_limit_retries: int = _RATE_LIMIT_RETRIES,
        rate_limit_sleep: float = _RATE_LIMIT_SLEEP_S,
    ):
        if ticker_factory is None:
            import yfinance as yf

            ticker_factory = yf.Ticker
        if download_fn is _DOWNLOAD_DEFAULT:
            import yfinance as yf

            download_fn = yf.download
        # download_fn=None disables batching (tests / forced sequential).
        self._factory = ticker_factory
        self._download = download_fn
        self._with_market_state = with_market_state
        self._rate_limit_retries = max(0, int(rate_limit_retries))
        self._rate_limit_sleep = max(0.0, float(rate_limit_sleep))

    def get_quote(self, symbol: str) -> Quote:
        # yfinance + newest pandas emit deprecation warnings that users cannot act on.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self._get_quote_with_retry(symbol)

    def get_quotes(self, symbols: list[str]) -> list[QuoteResult]:
        """Batch-friendly fetch: one download for history, then light per-symbol enrich.

        Falls back to the base sequential path if the batch download is unavailable
        or fails for a non-rate-limit reason. Market state is fetched once and shared
        across US tickers to cut Yahoo requests (get_info is expensive).
        """
        cleaned = [s.upper().strip() for s in symbols if s and str(s).strip()]
        if not cleaned:
            return []
        if len(cleaned) == 1 or self._download is None:
            return super().get_quotes(cleaned)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                hist_map = self._batch_history_with_retry(cleaned)
            except Exception as e:  # noqa: BLE001
                if _is_rate_limit(e):
                    tip = (
                        "Yahoo 限流 (Too Many Requests)。请稍后再试，"
                        "或拉长 watch 间隔（建议 ≥60 秒）"
                    )
                    return [QuoteResult(sym, error=f"数据源错误: {sym}: {tip}") for sym in cleaned]
                return super().get_quotes(cleaned)

        # yfinance often returns empty frames under rate limit instead of raising.
        if not any(hist_map.get(sym) is not None and len(hist_map.get(sym)) > 0 for sym in cleaned):
            tip = (
                "Yahoo 限流或暂无数据 (Too Many Requests / empty)。请稍后再试，"
                "或拉长 watch 间隔（建议 ≥60 秒）"
            )
            return [QuoteResult(sym, error=f"数据源错误: {sym}: {tip}") for sym in cleaned]

        results: list[QuoteResult] = []
        shared_state: Optional[str] = None
        state_fetched = False
        for sym in cleaned:
            try:
                hist = hist_map.get(sym)
                if hist is None or len(hist) == 0:
                    raise InvalidTickerError("没有行情数据,代码可能无效,或网络/Yahoo 不可用")
                quote = self._quote_from_hist(sym, hist)
                quote = self._enrich_live(sym, quote)
                if self._with_market_state:
                    if not state_fetched:
                        shared_state = self._market_state(sym)
                        state_fetched = True
                    quote.market_state = shared_state
                    closed = (
                        shared_state is not None
                        and shared_state.upper() in {"CLOSED", "POSTPOST", "PREPRE"}
                    )
                    if closed:
                        quote.is_last_close = True
                    elif shared_state is not None:
                        # Known open/pre/post session: trust live flag from fast_info.
                        pass
                results.append(QuoteResult(sym, quote=quote))
            except InvalidTickerError as e:
                results.append(QuoteResult(sym, error=f"无效代码或无数据 ({e})"))
            except SourceError as e:
                results.append(QuoteResult(sym, error=f"数据源错误: {e}"))
            except Exception as e:  # noqa: BLE001
                if _is_rate_limit(e):
                    results.append(QuoteResult(sym, error=f"数据源错误: {_rate_limit_error(sym)}"))
                else:
                    results.append(
                        QuoteResult(sym, error=f"未知错误: {type(e).__name__}: {e}")
                    )
        return results

    def _get_quote_with_retry(self, symbol: str) -> Quote:
        attempts = self._rate_limit_retries + 1
        last_rl: Optional[BaseException] = None
        for i in range(attempts):
            try:
                return self._get_quote(symbol)
            except SourceError:
                raise
            except Exception as e:  # noqa: BLE001
                if _is_rate_limit(e):
                    last_rl = e
                    if i + 1 < attempts and self._rate_limit_sleep > 0:
                        time.sleep(self._rate_limit_sleep)
                        continue
                    raise _rate_limit_error(symbol.upper().strip()) from e
                raise SourceError(
                    f"{symbol.upper().strip()}: {type(e).__name__}: {e}"
                ) from e
        assert last_rl is not None
        raise _rate_limit_error(symbol.upper().strip()) from last_rl

    def _get_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper().strip()
        try:
            t = self._factory(symbol)
            hist = t.history(period="5d", interval="1d", auto_adjust=False)
        except Exception as e:  # yfinance raises many different types
            if _is_rate_limit(e):
                raise
            raise SourceError(f"{symbol}: {type(e).__name__}: {e}") from e

        if hist is None or len(hist) == 0:
            raise InvalidTickerError("没有行情数据,代码可能无效,或网络/Yahoo 不可用")

        quote = self._quote_from_hist(symbol, hist)
        quote = self._enrich_live(symbol, quote, ticker=t)

        if self._with_market_state:
            state = self._market_state(symbol, ticker=t)
            quote.market_state = state
            closed = state is not None and state.upper() in {"CLOSED", "POSTPOST", "PREPRE"}
            live = not quote.is_last_close
            quote.is_last_close = closed or (state is None and not live)
        return quote

    def _quote_from_hist(self, symbol: str, hist) -> Quote:
        closes = [c for c in (_num(x) for x in hist["Close"]) if c is not None]
        if not closes:
            raise InvalidTickerError("没有有效收盘价")
        last_row = hist.iloc[-1]
        vol = _num(last_row.get("Volume"))
        return Quote(
            symbol=symbol,
            price=closes[-1],
            prev_close=closes[-2] if len(closes) >= 2 else None,
            day_high=_num(last_row.get("High")),
            day_low=_num(last_row.get("Low")),
            volume=int(vol) if vol is not None else None,
            market_state=None,
            is_last_close=True,  # until fast_info proves otherwise
        )

    def _enrich_live(self, symbol: str, quote: Quote, ticker=None) -> Quote:
        try:
            t = ticker if ticker is not None else self._factory(symbol)
            fi = t.fast_info
            lp = _num(fi["last_price"])
            pc = _num(fi["previous_close"])
            if lp is not None:
                quote.price = lp
                quote.is_last_close = False
            if pc is not None:
                quote.prev_close = pc
            quote.day_high = _num(fi["day_high"]) or quote.day_high
            quote.day_low = _num(fi["day_low"]) or quote.day_low
        except Exception as e:  # noqa: BLE001 - fall back to history values
            if _is_rate_limit(e):
                raise
        return quote

    def _market_state(self, symbol: str, ticker=None) -> Optional[str]:
        try:
            t = ticker if ticker is not None else self._factory(symbol)
            return t.get_info().get("marketState")
        except Exception:  # noqa: BLE001 - optional field; never fail the quote
            return None

    def _batch_history_with_retry(self, symbols: list[str]) -> dict[str, Any]:
        """Retry batch download when Yahoo rate-limits or returns an empty frame.

        yfinance often yields empty DataFrames under rate limit instead of raising,
        so we treat an all-empty result the same as an explicit rate-limit error.
        Non-rate-limit exceptions propagate so get_quotes can fall back to sequential.
        """
        attempts = self._rate_limit_retries + 1
        last_rl: Optional[BaseException] = None
        last_map: dict[str, Any] = {}
        for i in range(attempts):
            try:
                hist_map = self._batch_history(symbols)
            except Exception as e:  # noqa: BLE001
                if not _is_rate_limit(e):
                    raise
                last_rl = e
                hist_map = {}
            last_map = hist_map
            if any(hist_map.get(sym) is not None and len(hist_map.get(sym)) > 0 for sym in symbols):
                return hist_map
            if i + 1 < attempts and self._rate_limit_sleep > 0:
                time.sleep(self._rate_limit_sleep)
        if last_rl is not None and not any(
            last_map.get(sym) is not None and len(last_map.get(sym)) > 0 for sym in symbols
        ):
            raise last_rl
        return last_map

    def _batch_history(self, symbols: list[str]) -> dict[str, Any]:
        """Return {SYMBOL: DataFrame} using a single yf.download call."""
        import pandas as pd

        raw = self._download(
            tickers=symbols,
            period="5d",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            threads=False,
            progress=False,
        )
        out: dict[str, Any] = {}
        if raw is None or getattr(raw, "empty", True):
            return out

        # Multi-ticker: columns MultiIndex (symbol, field)
        if isinstance(raw.columns, pd.MultiIndex):
            level0 = set(raw.columns.get_level_values(0))
            for sym in symbols:
                if sym in level0:
                    df = raw[sym].dropna(how="all")
                    if len(df) > 0:
                        out[sym] = df
            return out

        # Single-ticker download shape (shouldn't happen for len>1, but be safe)
        if len(symbols) == 1:
            df = raw.dropna(how="all")
            if len(df) > 0:
                out[symbols[0]] = df
        return out
