from conftest import q

from stock_tool.alerts import AlertEngine
from stock_tool.models import AlertRule


def test_change_and_pct():
    x = q(price=110, prev=100)
    assert x.change == 10
    assert round(x.change_pct, 6) == 10.0
    assert q(prev=None).change is None
    assert q(prev=0).change_pct is None


def test_price_above_fires_once_per_crossing():
    eng = AlertEngine([AlertRule("AAPL", above=105)])
    assert eng.check(q(price=100)) == []
    ev = eng.check(q(price=106))
    assert [e.kind for e in ev] == ["above"]
    assert eng.check(q(price=107)) == []  # still above: no spam
    assert eng.check(q(price=104)) == []  # re-armed
    assert len(eng.check(q(price=106))) == 1  # fires again on new crossing


def test_price_below():
    eng = AlertEngine([AlertRule("AAPL", below=95)])
    assert eng.check(q(price=96)) == []
    assert [e.kind for e in eng.check(q(price=94))] == ["below"]
    assert eng.check(q(price=90)) == []


def test_pct_alerts():
    eng = AlertEngine([AlertRule("AAPL", pct_above=3, pct_below=-3)])
    assert eng.check(q(price=102, prev=100)) == []
    assert [e.kind for e in eng.check(q(price=103.5, prev=100))] == ["pct_above"]
    assert [e.kind for e in eng.check(q(price=96, prev=100))] == ["pct_below"]


def test_fires_if_already_true_on_first_observation():
    eng = AlertEngine([AlertRule("AAPL", above=90)])
    assert len(eng.check(q(price=100))) == 1
    assert eng.check(q(price=100)) == []


def test_unknown_symbol_and_missing_prev_close():
    eng = AlertEngine([AlertRule("AAPL", pct_above=1)])
    assert eng.check(q("MSFT", price=1000)) == []
    assert eng.check(q(price=100, prev=None)) == []  # pct unknown: skipped


def test_message():
    eng = AlertEngine([AlertRule("AAPL", above=105)])
    msg = eng.check(q(price=106, prev=100))[0].message()
    assert "AAPL" in msg and "106.00" in msg and "+6.00%" in msg
