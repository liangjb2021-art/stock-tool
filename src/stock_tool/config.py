"""Watchlist loading (YAML / TOML) and CLI alert specs."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Optional

from .models import AlertRule, Watchlist

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

DEFAULT_FILES = ("watchlist.yaml", "watchlist.yml", "watchlist.toml")
_KEYS = ("above", "below", "pct_above", "pct_below")


class ConfigError(Exception):
    pass


def normalize_symbol(s: str) -> str:
    return str(s).strip().upper()


def _rule_from(symbol: str, opts: Any) -> AlertRule:
    if opts is None:
        opts = {}
    if not isinstance(opts, dict):
        raise ConfigError(f"{symbol}: 告警配置应为键值对,实际为 {type(opts).__name__}")
    unknown = set(opts) - set(_KEYS) - {"symbol"}
    if unknown:
        raise ConfigError(f"{symbol}: 未知字段 {sorted(unknown)},可用字段: {list(_KEYS)}")
    vals = {}
    for k in _KEYS:
        if opts.get(k) is not None:
            try:
                vals[k] = float(opts[k])
            except (TypeError, ValueError):
                raise ConfigError(f"{symbol}.{k}: 需要数字,得到 {opts[k]!r}") from None
    return AlertRule(symbol=symbol, **vals)


def parse_watchlist(data: Any) -> Watchlist:
    if not isinstance(data, dict):
        raise ConfigError("配置文件顶层应为键值对,包含 tickers 字段")
    wl = Watchlist()
    if data.get("interval") is not None:
        try:
            wl.interval = float(data["interval"])
        except (TypeError, ValueError):
            raise ConfigError(f"interval 需要数字,得到 {data['interval']!r}") from None
    tickers = data.get("tickers", [])
    if isinstance(tickers, dict):  # {AAPL: {above: 1}, MSFT: null}
        for sym, opts in tickers.items():
            wl.rules.append(_rule_from(normalize_symbol(sym), opts))
    elif isinstance(tickers, list):  # [AAPL, {symbol: MSFT, above: 1}]
        for item in tickers:
            if isinstance(item, str):
                wl.rules.append(AlertRule(normalize_symbol(item)))
            elif isinstance(item, dict) and item.get("symbol"):
                sym = normalize_symbol(item["symbol"])
                wl.rules.append(_rule_from(sym, item))
            else:
                raise ConfigError(f"无法识别的 tickers 条目: {item!r}")
    else:
        raise ConfigError("tickers 应为列表或键值对")
    return wl


def load_watchlist(path: str | Path) -> Watchlist:
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"找不到配置文件: {p}")
    try:
        if p.suffix.lower() == ".toml":
            data = tomllib.loads(p.read_text(encoding="utf-8"))
        else:
            import yaml

            data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ConfigError(f"解析 {p} 失败: {e}") from e
    return parse_watchlist(data or {})


def find_default_config(cwd: Optional[Path] = None) -> Optional[Path]:
    base = cwd or Path.cwd()
    for name in DEFAULT_FILES:
        if (base / name).is_file():
            return base / name
    return None


_SPEC = re.compile(r"^\s*([A-Za-z][A-Za-z0-9.\-^=]*)\s*(%?)\s*(>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_alert_spec(spec: str) -> tuple[str, str, float]:
    """'AAPL>200' -> price above; 'AAPL<150' -> price below;
    'AAPL%>3' -> day change >= 3%; 'AAPL%<-3' -> day change <= -3%."""
    m = _SPEC.match(spec)
    if not m:
        raise ConfigError(
            f"无法解析告警 {spec!r}。格式示例: AAPL>200  AAPL<150  AAPL%>3  AAPL%<-3"
        )
    sym, pct, op, val = m.groups()
    kind = ("pct_" if pct else "") + ("above" if op.startswith(">") else "below")
    return normalize_symbol(sym), kind, float(val)


def build_watchlist(
    config_path: Optional[str],
    tickers: list[str],
    alert_specs: list[str],
) -> Watchlist:
    """Merge config file (explicit path, or default file if no CLI tickers) with CLI args."""
    wl = Watchlist()
    path: Optional[Path] = Path(config_path) if config_path else None
    if path is None and not tickers:
        path = find_default_config()
    if path is not None:
        wl = load_watchlist(path)
    for t in tickers:
        sym = normalize_symbol(t)
        if sym not in wl.symbols:
            wl.rules.append(AlertRule(sym))
    for spec in alert_specs:
        sym, kind, val = parse_alert_spec(spec)
        setattr(wl.rule_for(sym), kind, val)
    # de-duplicate while keeping order
    seen: set[str] = set()
    uniq = []
    for r in wl.rules:
        if r.symbol not in seen:
            seen.add(r.symbol)
            uniq.append(r)
    wl.rules = uniq
    return wl
