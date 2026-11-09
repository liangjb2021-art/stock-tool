"""YFinanceSource against a fake yfinance.Ticker (no network)."""
import pandas as pd
import pytest

from stock_tool.sources import InvalidTickerError, SourceError, YFinanceSource
from stock_tool.sources.yfinance_source import _is_rate_limit


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


class RateLimitError(Exception):
    """Mimic yfinance.exceptions.YFRateLimitError by name substring."""


HIST = pd.DataFrame(
    {"Close": [100.0, 102.0], "High": [101.0, 104.0], "Low": [99.0, 101.0], "Volume": [1000, 2000]}
)


def src(**kw):
    retries = kw.pop("rate_limit_retries", 0)
    sleep = kw.pop("rate_limit_sleep", 0.0)
    download_fn = kw.pop("download_fn", None)
    return YFinanceSource(
        ticker_factory=lambda s: FakeTicker(s, **kw),
        download_fn=download_fn,
        rate_limit_retries=retries,
        rate_limit_sleep=sleep,
    )


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


def test_get_quotes_isolates_failures_sequential():
    def factory(s):
        if s == "BAD":
            return FakeTicker(s, hist=pd.DataFrame())
        if s == "NET":
            return FakeTicker(s, boom=ConnectionError("down"))
        return FakeTicker(s, hist=HIST, info={"marketState": "CLOSED"})

    res = YFinanceSource(
        ticker_factory=factory,
        download_fn=None,  # force sequential path
        rate_limit_retries=0,
        rate_limit_sleep=0,
    ).get_quotes(["AAPL", "BAD", "NET"])
    assert [r.ok for r in res] == [True, False, False]
    assert "无效" in res[1].error and "数据源错误" in res[2].error


def test_batch_get_quotes_uses_download_and_shares_market_state():
    info_calls = []

    class CountingTicker(FakeTicker):
        def get_info(self):
            info_calls.append(self.symbol)
            return {"marketState": "CLOSED"}

    def fake_download(**kw):
        cols = pd.MultiIndex.from_product([["AAPL", "MSFT"], ["Close", "High", "Low", "Volume"]])
        return pd.DataFrame(
            [
                [100, 101, 99, 1000, 200, 201, 199, 3000],
                [102, 104, 101, 2000, 210, 212, 208, 4000],
            ],
            columns=cols,
        )

    res = YFinanceSource(
        ticker_factory=lambda s: CountingTicker(
            s,
            hist=HIST,
            fast={"last_price": 103.0, "previous_close": 102.0, "day_high": 105.0, "day_low": 101.0},
        ),
        download_fn=fake_download,
        rate_limit_retries=0,
        rate_limit_sleep=0,
    ).get_quotes(["AAPL", "MSFT"])
    assert [r.ok for r in res] == [True, True]
    assert res[0].quote.price == 103.0 and res[1].quote.price == 103.0
    assert res[0].quote.market_state == "CLOSED" and res[1].quote.market_state == "CLOSED"
    assert res[0].quote.is_last_close and res[1].quote.is_last_close
    assert len(info_calls) == 1  # shared market-state fetch


def test_batch_marks_missing_symbols_invalid():
    def fake_download(**kw):
        cols = pd.MultiIndex.from_product([["AAPL", "BAD"], ["Close", "High", "Low", "Volume"]])
        df = pd.DataFrame(
            [[100, 101, 99, 1000, float("nan"), float("nan"), float("nan"), float("nan")],
             [102, 104, 101, 2000, float("nan"), float("nan"), float("nan"), float("nan")]],
            columns=cols,
        )
        return df

    res = YFinanceSource(
        ticker_factory=lambda s: FakeTicker(s, hist=HIST, info={"marketState": "CLOSED"}),
        download_fn=fake_download,
        rate_limit_retries=0,
        rate_limit_sleep=0,
    ).get_quotes(["AAPL", "BAD"])
    assert res[0].ok and not res[1].ok and "无效" in res[1].error


def test_rate_limit_message_and_retry(monkeypatch):
    calls = {"n": 0}

    class BoomTicker(FakeTicker):
        def history(self, **kw):
            calls["n"] += 1
            raise RateLimitError("Too Many Requests. Rate limited.")

    sleeps = []
    monkeypatch.setattr("stock_tool.sources.yfinance_source.time.sleep", lambda s: sleeps.append(s))
    with pytest.raises(SourceError) as ei:
        YFinanceSource(
            ticker_factory=lambda s: BoomTicker(s),
            download_fn=None,
            rate_limit_retries=2,
            rate_limit_sleep=0.01,
        ).get_quote("AAPL")
    assert "限流" in str(ei.value)
    assert calls["n"] == 3
    assert sleeps == [0.01, 0.01]


def test_is_rate_limit_helper():
    assert _is_rate_limit(RateLimitError("Too Many Requests. Rate limited."))
    assert not _is_rate_limit(ConnectionError("down"))


def test_batch_all_empty_treated_as_rate_limit():
    def fake_download(**kw):
        cols = pd.MultiIndex.from_product([["AAPL", "MSFT"], ["Close", "High", "Low", "Volume"]])
        import numpy as np
        return pd.DataFrame(np.nan, index=[0, 1], columns=cols)

    res = YFinanceSource(
        ticker_factory=lambda s: FakeTicker(s, hist=HIST),
        download_fn=fake_download,
        rate_limit_retries=0,
        rate_limit_sleep=0,
    ).get_quotes(["AAPL", "MSFT"])
    assert all(not r.ok for r in res)
    assert all("限流" in r.error for r in res)


def test_batch_empty_then_retry_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps = []
    monkeypatch.setattr("stock_tool.sources.yfinance_source.time.sleep", lambda s: sleeps.append(s))

    def fake_download(**kw):
        calls["n"] += 1
        cols = pd.MultiIndex.from_product([["AAPL", "MSFT"], ["Close", "High", "Low", "Volume"]])
        if calls["n"] == 1:
            import numpy as np
            return pd.DataFrame(np.nan, index=[0, 1], columns=cols)
        return pd.DataFrame(
            [
                [100, 101, 99, 1000, 200, 201, 199, 3000],
                [102, 104, 101, 2000, 210, 212, 208, 4000],
            ],
            columns=cols,
        )

    res = YFinanceSource(
        ticker_factory=lambda s: FakeTicker(
            s,
            hist=HIST,
            fast={"last_price": 103.0, "previous_close": 102.0, "day_high": 105.0, "day_low": 101.0},
            info={"marketState": "CLOSED"},
        ),
        download_fn=fake_download,
        rate_limit_retries=1,
        rate_limit_sleep=0.01,
    ).get_quotes(["AAPL", "MSFT"])
    assert [r.ok for r in res] == [True, True]
    assert calls["n"] == 2
    assert sleeps == [0.01]


def test_batch_rate_limit_exception_then_retry_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps = []
    monkeypatch.setattr("stock_tool.sources.yfinance_source.time.sleep", lambda s: sleeps.append(s))

    def fake_download(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RateLimitError("Too Many Requests. Rate limited.")
        cols = pd.MultiIndex.from_product([["AAPL", "MSFT"], ["Close", "High", "Low", "Volume"]])
        return pd.DataFrame(
            [
                [100, 101, 99, 1000, 200, 201, 199, 3000],
                [102, 104, 101, 2000, 210, 212, 208, 4000],
            ],
            columns=cols,
        )

    res = YFinanceSource(
        ticker_factory=lambda s: FakeTicker(s, hist=HIST, info={"marketState": "CLOSED"}),
        download_fn=fake_download,
        rate_limit_retries=1,
        rate_limit_sleep=0.01,
    ).get_quotes(["AAPL", "MSFT"])
    assert all(r.ok for r in res)
    assert calls["n"] == 2
    assert sleeps == [0.01]


def test_batch_empty_retries_then_still_rate_limit(monkeypatch):
    calls = {"n": 0}
    sleeps = []
    monkeypatch.setattr("stock_tool.sources.yfinance_source.time.sleep", lambda s: sleeps.append(s))

    def fake_download(**kw):
        calls["n"] += 1
        cols = pd.MultiIndex.from_product([["AAPL", "MSFT"], ["Close", "High", "Low", "Volume"]])
        import numpy as np
        return pd.DataFrame(np.nan, index=[0, 1], columns=cols)

    res = YFinanceSource(
        ticker_factory=lambda s: FakeTicker(s, hist=HIST),
        download_fn=fake_download,
        rate_limit_retries=2,
        rate_limit_sleep=0.01,
    ).get_quotes(["AAPL", "MSFT"])
    assert all(not r.ok for r in res)
    assert all("限流" in r.error for r in res)
    assert calls["n"] == 3
    assert sleeps == [0.01, 0.01]
