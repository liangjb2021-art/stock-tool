# stock-tool

美股盯盘命令行工具:一次性报价、循环盯盘、价格/涨跌幅提醒。数据来自 Yahoo Finance(通过开源库 `yfinance`),无需 API Key。

*English: a small CLI to quote and watch US stocks with price / %-change alerts. Data via `yfinance` (no API key). Not investment advice.*

## 功能

- `quote`:一次性表格,显示最新价、涨跌、涨跌幅、日内最高/最低、成交量、市场状态(基于 `rich`)
- `watch`:按间隔循环刷新,条件触发时打印提醒(可选终端响铃、桌面通知)
- 告警:价格高于/低于某值、当日涨跌幅高于/低于某阈值;**每次穿越只提醒一次**,条件恢复后自动重新计数,不会刷屏
- 自选股来自配置文件(YAML 或 TOML)和/或命令行参数
- 容错:无效代码、网络失败只影响对应股票,不会中断其它股票和监控循环;休市时显示最近收盘价(代码后带 `*`)。多标的报价会合并历史行情请求,并对 Yahoo 限流做短退避重试
- 可插拔数据源:实现 `DataSource` 接口即可接入其它免费数据源,默认实现为 `YFinanceSource`
- 测试不访问网络(数据层被 mock);CI 工作流(Python 3.10–3.13)位于 `.github/workflows/ci.yml`,对 push/PR 自动运行

## 安装

需要 Python 3.10+。

```bash
git clone https://github.com/liangjb2021-art/stock-tool.git
cd stock-tool
pip install -e .          # 开发/测试: pip install -e ".[dev]"
```

## 使用

```bash
# 一次性报价
stock-tool quote AAPL MSFT NVDA

# 盯盘:每 60 秒刷新,AAPL 价格 >= 250 或当日涨幅 >= 3% 时提醒
stock-tool watch AAPL MSFT -a 'AAPL>250' -a 'AAPL%>3' --interval 60

# 使用配置文件(未指定 -c 时自动读取当前目录的 watchlist.yaml / .yml / .toml)
cp watchlist.example.yaml watchlist.yaml
stock-tool watch
stock-tool quote -c watchlist.example.toml

# 提醒时同时发桌面通知(Linux: notify-send;macOS: osascript);--no-bell 关闭响铃
stock-tool watch --notify
```

命令行告警写法(`-a/--alert`,可重复):

| 写法 | 含义 |
| --- | --- |
| `AAPL>250` | 价格 ≥ 250 |
| `AAPL<200` | 价格 ≤ 200 |
| `AAPL%>3` | 当日涨跌幅 ≥ +3% |
| `AAPL%<-3` | 当日涨跌幅 ≤ -3%(注意写负数) |

命令行参数会与配置文件合并,同一只股票的同类告警以命令行为准。

## 配置示例

`watchlist.yaml`(TOML 版本见 `watchlist.example.toml`):

```yaml
interval: 60          # 刷新间隔(秒),可被 --interval 覆盖
tickers:
  AAPL:
    above: 250        # 价格 >= 250
    below: 200        # 价格 <= 200
    pct_above: 3      # 当日涨跌幅 >= 3%
    pct_below: -3     # 当日涨跌幅 <= -3%
  MSFT:
    above: 600
  NVDA:               # 只盯盘,不设告警
```

`tickers` 也可以写成列表:`- AAPL` 或 `- {symbol: TSLA, below: 150}`。刷新间隔最低 5 秒,避免被 Yahoo 限流。

## 开发与测试

```bash
pip install -e ".[dev]"
pytest
```

包结构:`src/stock_tool/`(`cli.py` 命令行、`config.py` 配置、`alerts.py` 告警引擎、`display.py` 表格、`notify.py` 通知、`sources/` 数据源)。新增数据源:继承 `stock_tool.sources.base.DataSource`,实现 `get_quote(symbol) -> Quote`,并在 `cli.make_source()` 中切换。

## 数据来源说明

数据来自 Yahoo Finance,通过开源库 [`yfinance`](https://github.com/ranaroussi/yfinance) 获取(当前兼容 0.2.x 与 1.x,PyPI 最新为 1.8.x)。这是**非官方**接口,仅供个人研究和学习使用;数据可能延迟(通常约 15 分钟或更久)、可能出错,接口也可能随时变更或被限流。请遵守 Yahoo 的使用条款。若频繁出现 `Too Many Requests`,请加大 `--interval` 或稍后再试。

## 免责声明

本工具及其输出**不构成任何投资建议**。使用者应自行判断并承担全部投资风险;作者不对因使用本工具造成的任何损失负责。

## 频道 / 关注

作者在宽客汇 QuantHub 的个人频道「股票研究员」:<https://haimao.app/users/kuanke_stock> ,定期发布带可复现回测的美股/A股事件研究短文。近期几篇:

- [美元指数创19个月新高：历史上美元这么强之后，美股下个月反而更差吗？](https://haimao.app/posts/135)
- [创业板一天跌3.3%、上证只跌0.6%：今年第8次了，之后一周是弹还是接着跌？](https://haimao.app/posts/134)
- [黄金一周跌4.6%、12周跌了9周：历史上急跌之后，一个月会弹回来吗？](https://haimao.app/posts/133)
- [超微一周涨近19%，周五却一天跌8.8%：历史上砸完这么狠会自动弹吗？](https://haimao.app/posts/130)
- [费半周五跌3.7%，当周却还涨了9%：历史上周五砸完，两周后会修复吗？](https://haimao.app/posts/129)
- [周五必需品涨1.4%、科技跌2%：历史上科技接下来一个月更弱吗？](https://haimao.app/posts/128)

## License

[MIT](LICENSE)
