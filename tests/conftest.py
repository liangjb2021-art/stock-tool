import pytest

from stock_tool.models import Quote, QuoteResult
from stock_tool.sources.base import DataSource, InvalidTickerError, SourceError


class FakeSource(DataSource):
    """Scripted data source: no network. `script[symbol]` is a list of Quote/Exception,
    consumed one per call (the last item repeats)."""

    name = "fake"

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = 0

    def get_quote(self, symbol):
        self.calls += 1
        items = self.script.get(symbol)
        if items is None:
            raise InvalidTickerError(symbol)
        item = items.pop(0) if len(items) > 1 else items[0]
        if isinstance(item, Exception):
            raise item
        return item


def q(symbol="AAPL", price=100.0, prev=100.0, **kw):
    return Quote(symbol=symbol, price=price, prev_close=prev, **kw)


@pytest.fixture
def fake_source_factory():
    return FakeSource
