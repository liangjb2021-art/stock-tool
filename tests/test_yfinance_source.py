"""YFinanceSource against a fake yfinance.Ticker (no network)."""
import pandas as pd
import pytest

from stock_tool.sources import InvalidTickerError, SourceError, YFinanceSource


class FakeTicker:
    def __init__(self, symbol, hist=None, fast=None, info=None, boom=None):
        self.symbol, self._hist, self._fast, self._info, self._boom = symbol, hist, fast, info, boom

    def history(self, **kw):
        if self._boom:
            raise self._boom
        return self._hist if self._hist is not None else pd.DataFrame()

    @property
    def fast_info(self):
        if self._fast is None:
            raise RuntimeError("no fast_info")
        return self._fast

    def get_info(self):
        if self._info is None:
            raise RuntimeError("no info")
        return self._info


HIST = pd.DataFrame(
    {"Close": [100.0, 102.0], "High": [101.0, 104.0], "Low": [99.0, 101.0], "Volume": [1000, 2000]}
)


def src(**kw):
    return YFinanceSource(ticker_factory=lambda s: FakeTicker(s, **kw))


def test_live_quote_uses_fast_info():
    fast = {"last_price": 103.5, "previous_close": 102.0, "day_high": 105.0, "day_low": 101.0}
    q = src(hist=HIST, fast=fast, info={"marketState": "REGULAR"}).get_quote("aapl")
    assert (q.symbol, q.price, q.prev_close, q.day_high, q.day_low) == ("AAPL", 103.5, 102.0, 105.0, 101.0)
    assert q.volume == 2000 and q.market_state == "REGULAR" and not q.is_last_close


def test_market_closed_falls_back_to_last_close():
    q = src(hist=HIST, fast=None, info={"marketState": "CLOSED"}).get_quote("AAPL")
    assert q.price == 102.0 and q.prev_close == 100.0 and q.is_last_close


def test_history_only_when_everything_else_fails():
    q = src(hist=HIST).get_quote("AAPL")
    assert q.price == 102.0 and q.market_state is None and q.is_last_close


def test_invalid_ticker_empty_history():
    with pytest.raises(InvalidTickerError):
        src(hist=pd.DataFrame()).get_quote("ZZZZ")


def test_network_error_becomes_source_error():
    with pytest.raises(SourceError):
        src(boom=ConnectionError("down")).get_quote("AAPL")


def test_get_quotes_isolates_failures():
    def factory(s):
        if s == "BAD":
            return FakeTicker(s, hist=pd.DataFrame())
        if s == "NET":
            return FakeTicker(s, boom=ConnectionError("down"))
        return FakeTicker(s, hist=HIST, info={"marketState": "CLOSED"})

    res = YFinanceSource(ticker_factory=factory).get_quotes(["AAPL", "BAD", "NET"])
    assert [r.ok for r in res] == [True, False, False]
    assert "无效" in res[1].error and "数据源错误" in res[2].error
