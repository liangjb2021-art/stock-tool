"""Data-source interface. Implement DataSource to plug in another free source."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Quote, QuoteResult


class SourceError(Exception):
    """Generic data-source failure (network, rate limit, parsing...)."""


class InvalidTickerError(SourceError):
    """The source has no data for this ticker."""


class DataSource(ABC):
    name: str = "base"

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        """Return a Quote for `symbol`.

        Raise InvalidTickerError if the ticker is unknown, SourceError for any
        other failure. If the market is closed, return the last close and set
        Quote.is_last_close = True.
        """

    def get_quotes(self, symbols: list[str]) -> list[QuoteResult]:
        """Fetch many symbols; one failure never aborts the rest."""
        results: list[QuoteResult] = []
        for sym in symbols:
            try:
                results.append(QuoteResult(sym, quote=self.get_quote(sym)))
            except InvalidTickerError as e:
                results.append(QuoteResult(sym, error=f"无效代码或无数据 ({e})"))
            except SourceError as e:
                results.append(QuoteResult(sym, error=f"数据源错误: {e}"))
            except Exception as e:  # noqa: BLE001 - never crash the watch loop
                results.append(QuoteResult(sym, error=f"未知错误: {type(e).__name__}: {e}"))
        return results
