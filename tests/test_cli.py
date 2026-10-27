import pytest
from conftest import FakeSource, q
from rich.console import Console

import stock_tool.cli as cli
from stock_tool.sources.base import SourceError


def run(monkeypatch, capsys, source, argv):
    monkeypatch.setattr(cli, "make_source", lambda: source)
    monkeypatch.setattr(cli, "bell", lambda: None)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    monkeypatch.setattr(cli, "Console", lambda: Console(width=160, force_terminal=False))
    rc = cli.main(argv)
    return rc, capsys.readouterr().out


def test_quote_table(monkeypatch, capsys):
    src = FakeSource({
        "AAPL": [q("AAPL", 110, 100, day_high=111, day_low=99, volume=12345, market_state="REGULAR")],
        "MSFT": [q("MSFT", 90, 100, market_state="CLOSED", is_last_close=True)],
    })
    rc, out = run(monkeypatch, capsys, src, ["quote", "AAPL", "MSFT", "NOPE"])
    assert rc == 0
    assert "110.00" in out and "+10.00%" in out and "12,345" in out
    assert "-10.00%" in out and "MSFT*" in out and "最近收盘价" in out
    assert "NOPE" in out and "无效代码" in out


def test_quote_all_fail_exit_code(monkeypatch, capsys):
    rc, out = run(monkeypatch, capsys, FakeSource({"AAPL": [SourceError("timeout")]}), ["quote", "AAPL"])
    assert rc == 1 and "数据源错误" in out


def test_quote_no_tickers(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    rc, out = run(monkeypatch, capsys, FakeSource({}), ["quote"])
    assert rc == 2


def test_bad_config_exit_code(monkeypatch, capsys):
    rc, out = run(monkeypatch, capsys, FakeSource({}), ["quote", "AAPL", "-a", "garbage"])
    assert rc == 2 and "配置错误" in out


def test_watch_alert_fires_once_per_crossing(monkeypatch, capsys):
    prices = [100, 106, 107, 104, 106]
    src = FakeSource({"AAPL": [q("AAPL", p, 100) for p in prices]})
    rc, out = run(monkeypatch, capsys, src,
                  ["watch", "AAPL", "-a", "AAPL>105", "-i", "5", "--max-iterations", str(len(prices))])
    assert rc == 0
    assert out.count("触发告警") == 2  # 100->106 and 104->106, not 107


def test_watch_survives_errors(monkeypatch, capsys):
    src = FakeSource({"AAPL": [SourceError("net down"), q("AAPL", 106, 100)]})
    rc, out = run(monkeypatch, capsys, src,
                  ["watch", "AAPL", "-a", "AAPL>105", "--max-iterations", "2"])
    assert rc == 0 and "net down" in out and out.count("触发告警") == 1


def test_watch_interval_from_config(monkeypatch, capsys, tmp_path):
    f = tmp_path / "w.yaml"
    f.write_text("interval: 42\ntickers:\n  AAPL:\n    above: 1\n")
    src = FakeSource({"AAPL": [q("AAPL", 10, 10)]})
    rc, out = run(monkeypatch, capsys, src, ["watch", "-c", str(f), "--max-iterations", "1"])
    assert rc == 0 and "每 42 秒" in out


def test_watch_notify_flag(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(cli, "desktop_notify", lambda t, m: sent.append(m))
    src = FakeSource({"AAPL": [q("AAPL", 106, 100)]})
    run(monkeypatch, capsys, src, ["watch", "AAPL", "-a", "AAPL>105", "--notify", "--max-iterations", "1"])
    assert len(sent) == 1
