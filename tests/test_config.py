import pytest

from stock_tool.config import (
    ConfigError,
    build_watchlist,
    load_watchlist,
    parse_alert_spec,
)


def test_load_yaml_mapping(tmp_path):
    f = tmp_path / "w.yaml"
    f.write_text("interval: 30\ntickers:\n  aapl:\n    above: 250\n    pct_below: -3\n  MSFT:\n")
    wl = load_watchlist(f)
    assert wl.interval == 30
    assert wl.symbols == ["AAPL", "MSFT"]
    assert wl.rules[0].above == 250 and wl.rules[0].pct_below == -3
    assert wl.rules[1].is_empty()


def test_load_yaml_list(tmp_path):
    f = tmp_path / "w.yaml"
    f.write_text("tickers:\n  - nvda\n  - {symbol: tsla, below: 150}\n")
    wl = load_watchlist(f)
    assert wl.symbols == ["NVDA", "TSLA"]
    assert wl.rules[1].below == 150


def test_load_toml(tmp_path):
    f = tmp_path / "w.toml"
    f.write_text("interval = 20\n[tickers.AAPL]\nabove = 1.5\n[tickers.MSFT]\n")
    wl = load_watchlist(f)
    assert wl.interval == 20 and wl.rules[0].above == 1.5 and wl.symbols == ["AAPL", "MSFT"]


def test_bad_config(tmp_path):
    f = tmp_path / "w.yaml"
    f.write_text("tickers:\n  AAPL:\n    abov: 1\n")
    with pytest.raises(ConfigError):
        load_watchlist(f)
    f.write_text("tickers:\n  AAPL:\n    above: abc\n")
    with pytest.raises(ConfigError):
        load_watchlist(f)
    with pytest.raises(ConfigError):
        load_watchlist(tmp_path / "missing.yaml")
    f.write_text("tickers: [unclosed")
    with pytest.raises(ConfigError):
        load_watchlist(f)


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("AAPL>200", ("AAPL", "above", 200.0)),
        ("aapl<150.5", ("AAPL", "below", 150.5)),
        ("AAPL%>3", ("AAPL", "pct_above", 3.0)),
        ("AAPL%<-3", ("AAPL", "pct_below", -3.0)),
        ("BRK-B > 400", ("BRK-B", "above", 400.0)),
    ],
)
def test_parse_alert_spec(spec, expected):
    assert parse_alert_spec(spec) == expected


def test_parse_alert_spec_invalid():
    with pytest.raises(ConfigError):
        parse_alert_spec("AAPL=200")


def test_build_watchlist_merges_cli_over_config(tmp_path, monkeypatch):
    f = tmp_path / "w.yaml"
    f.write_text("tickers:\n  AAPL:\n    above: 250\n")
    wl = build_watchlist(str(f), ["msft", "AAPL"], ["AAPL>260", "MSFT%<-2"])
    assert wl.symbols == ["AAPL", "MSFT"]
    assert wl.rules[0].above == 260
    assert wl.rules[1].pct_below == -2


def test_default_config_discovery(tmp_path, monkeypatch):
    (tmp_path / "watchlist.yaml").write_text("tickers: [AAPL]\n")
    monkeypatch.chdir(tmp_path)
    assert build_watchlist(None, [], []).symbols == ["AAPL"]
    # explicit tickers on CLI skip the auto-discovered file
    assert build_watchlist(None, ["MSFT"], []).symbols == ["MSFT"]
