# Schwab Trinity Strategy Bot

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Platform](https://img.shields.io/badge/Broker-Charles%20Schwab-00a0df)
![Strategy](https://img.shields.io/badge/Strategy-Trinity%20Hybrid-orange)
![GCP](https://img.shields.io/badge/GCP-Cloud%20Run-4285F4)

[English](#english) | [中文](#中文)

---

<a id="english"></a>
## English

Automated trading service for Charles Schwab accounts, deployed on GCP Cloud Run. Allocates capital across three layers: **attack (TQQQ)** driven by QQQ MA200 + ATR bands with staged exits, **income (SPYI / QQQI)** when equity exceeds a threshold, and **defense (BOXX)** for idle cash. Each run fetches data, computes targets, places orders, and notifies via Telegram.

### Logic overview

- **Data**: QQQ (signals), TQQQ, SPYI, QQQI, BOXX; daily. Indicators: 200-day SMA (MA200), 14-day ATR%.
- **Bands (QQQ)**: `entry_line = MA200 * (1 + f(ATR%))`, `exit_line = MA200 * (1 - g(ATR%))`. TQQQ size and exits are driven by QQQ vs these levels.

### Attack layer (TQQQ)

- **Instrument**: TQQQ (3x Nasdaq).
- **Size**: `agg_ratio` from `get_hybrid_allocation(strategy_equity, qqq_p, exit_line)`; applied only to strategy-layer equity (total minus income layer).
- **Rules** (when holding TQQQ):
  - QQQ < exit_line → target TQQQ = 0 (full exit).
  - exit_line ≤ QQQ < MA200 → target = agg_ratio × 0.33 (staged reduction).
  - QQQ ≥ MA200 → target = agg_ratio (full allocation).
- **Entry**: If not holding TQQQ and QQQ > entry_line → target = agg_ratio.
- **Orders**: Sell TQQQ via market; buy TQQQ via limit at ask × 1.005.

### Income layer (SPYI / QQQI)

- **Purpose**: Dividend/income allocation when equity is large enough; not used for strategy-layer sizing.
- **Instruments**: SPYI (S&P 500 income), QQQI (Nasdaq income).
- **Activation**: `get_income_ratio(total_equity)` is 0 below `INCOME_THRESHOLD_USD` (default 100000); ramps to 40% by 2× threshold; capped at 60% above that.
- **Split**: `QQQI_INCOME_RATIO` (default 0.5) → QQQI share = income_ratio × QQQI_INCOME_RATIO, SPYI = remainder.
- **Rebalancing**: Targets are enforced each run; excess SPYI/QQQI is sold when above target.

### Defense layer (BOXX and cash)

- **Instrument**: BOXX (short-duration / cash-like).
- **Reserve**: `CASH_RESERVE_RATIO` (default 5%) of strategy equity is kept as cash.
- **Target**: Strategy equity minus reserve minus target TQQQ; surplus buying power after SPYI/QQQI/TQQQ orders is used to buy BOXX (market order) when enough for 2+ shares.

### Notifications

Beautiful emoji-formatted Telegram notifications with full i18n support.

**Trade execution:**
```
🔔 【Trade Execution Report】
📊 Signal: 💎 Trend Hold

📊 Dashboard | Equity: $1,418.96
TQQQ: $96.43 | SPYI: $0.00 | QQQI: $0.00 | BOXX: $0.00
Buying Power: $1,322.53 | Signal: 💎 Trend Hold
QQQ: 600.64 | MA200: 580.62 | Exit: 558.97
━━━━━━━━━━━━━━━━━━
✅ 💰 Limit Buy TQQQ ($48.45): 25 shares submitted (ID: xxx)
```

**Heartbeat (no trades):**
```
💓 【Heartbeat】
💰 Equity: $1,418.96
━━━━━━━━━━━━━━━━━━
TQQQ: $96.43  BOXX: $0.00
QQQI: $0.00  SPYI: $0.00
━━━━━━━━━━━━━━━━━━
🎯 Signal: 💎 Trend Hold
QQQ: 600.64 | MA200: 580.62 | Exit: 558.97
━━━━━━━━━━━━━━━━━━
✅ No rebalance needed
```

### Rebalance and orders

- **Frequency**: One full cycle per HTTP request (e.g. Cloud Scheduler on trading days).
- **Threshold**: Trades only when |current_mv − target_mv| > 1% of total equity per symbol.
- **Order types**: Limit buy at ask × 1.005 for TQQQ/SPYI/QQQI; market for BOXX buy and all sells.

### Environment variables

| Variable | Description |
|----------|-------------|
| `SCHWAB_API_KEY` | Schwab API key |
| `SCHWAB_APP_SECRET` | Schwab API secret |
| `TELEGRAM_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat ID |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID |
| `INCOME_THRESHOLD_USD` | Equity threshold to enable income layer (default 100000) |
| `QQQI_INCOME_RATIO` | QQQI share of income layer, 0–1 (default 0.5) |
| `NOTIFY_LANG` | Notification language: `en` (English, default) or `zh` (Chinese) |

Deploy as a Cloud Run service and trigger the root URL on a schedule (e.g. once per trading day). Entry point: Flask route `"/"` in `main.py`.

---

<a id="中文"></a>
## 中文

基于 Charles Schwab 账户的自动化交易服务，部署在 GCP Cloud Run 上。资金分配为三层：**进攻层 (TQQQ)** 基于 QQQ MA200 + ATR 波段分阶段退出，**收入层 (SPYI / QQQI)** 在资产超过阈值时启用，**防御层 (BOXX)** 管理闲置资金。每次运行获取数据、计算目标、下单并通过 Telegram 通知。

### 策略概览

- **数据**: QQQ（信号）、TQQQ、SPYI、QQQI、BOXX；日线级别。指标：200 日均线（MA200）、14 日 ATR%。
- **波段（QQQ）**: `入场线 = MA200 * (1 + f(ATR%))`，`止损线 = MA200 * (1 - g(ATR%))`。TQQQ 的仓位和退出由 QQQ 相对这些价位决定。

### 进攻层 (TQQQ)

- **标的**: TQQQ（三倍纳指）。
- **仓位**: `agg_ratio` 由 `get_hybrid_allocation(strategy_equity, qqq_p, exit_line)` 计算；仅应用于策略层资产（总资产减去收入层）。
- **规则**（持有 TQQQ 时）：
  - QQQ < 止损线 → 目标 TQQQ = 0（全部退出）。
  - 止损线 ≤ QQQ < MA200 → 目标 = agg_ratio × 0.33（分阶段减仓）。
  - QQQ ≥ MA200 → 目标 = agg_ratio（满配）。
- **入场**: 未持有 TQQQ 且 QQQ > 入场线 → 目标 = agg_ratio。
- **订单类型**: TQQQ 卖出用市价单；买入用限价单，价格 = ask × 1.005。

### 收入层 (SPYI / QQQI)

- **目的**: 大账户的分红/收入配置；不影响策略层仓位计算。
- **标的**: SPYI（标普收入 ETF）、QQQI（纳指收入 ETF）。
- **激活条件**: `get_income_ratio(total_equity)` 在 `INCOME_THRESHOLD_USD`（默认 100000）以下为 0；至 2 倍阈值线性增长至 40%；超出后上限 60%。
- **分配**: `QQQI_INCOME_RATIO`（默认 0.5）→ QQQI 占比 = income_ratio × QQQI_INCOME_RATIO，SPYI = 剩余部分。
- **再平衡**: 每次运行强制执行目标；SPYI/QQQI 超出目标时卖出。

### 防御层 (BOXX 和现金)

- **标的**: BOXX（短久期/类现金 ETF）。
- **现金储备**: 策略层资产的 `CASH_RESERVE_RATIO`（默认 5%）保持为现金。
- **目标**: 策略层资产减去储备减去目标 TQQQ；SPYI/QQQI/TQQQ 下单后剩余购买力用于买入 BOXX（市价单），至少 2 股起买。

### 通知格式

精美的 Emoji 格式 Telegram 通知，支持中英文切换。

**交易执行通知:**
```
🔔 【交易执行报告】
📊 信号: 💎 趋势持有

📊 资产看板 | 净值: $1,418.96
TQQQ: $96.43 | SPYI: $0.00 | QQQI: $0.00 | BOXX: $0.00
购买力: $1,322.53 | 信号: 💎 趋势持有
QQQ: 600.64 | MA200: 580.62 | Exit: 558.97
━━━━━━━━━━━━━━━━━━
✅ 💰 限价买入指令 TQQQ ($48.45): 25股 已下发 (ID: xxx)
```

**心跳通知 (无需调仓):**
```
💓 【心跳检测】
💰 净值: $1,418.96
━━━━━━━━━━━━━━━━━━
TQQQ: $96.43  BOXX: $0.00
QQQI: $0.00  SPYI: $0.00
━━━━━━━━━━━━━━━━━━
🎯 信号: 💎 趋势持有
QQQ: 600.64 | MA200: 580.62 | Exit: 558.97
━━━━━━━━━━━━━━━━━━
✅ 无需调仓
```

### 再平衡与订单

- **频率**: 每次 HTTP 请求执行一个完整周期（如 Cloud Scheduler 在交易日触发）。
- **阈值**: 仅当 |当前市值 − 目标市值| > 总资产的 1% 时触发交易。
- **订单类型**: TQQQ/SPYI/QQQI 买入用限价单（ask × 1.005）；BOXX 买入和所有卖出用市价单。

### 环境变量

| 变量 | 说明 |
|------|------|
| `SCHWAB_API_KEY` | Schwab API 密钥 |
| `SCHWAB_APP_SECRET` | Schwab API 密钥 |
| `TELEGRAM_TOKEN` | Telegram 机器人 Token |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID |
| `GOOGLE_CLOUD_PROJECT` | GCP 项目 ID |
| `INCOME_THRESHOLD_USD` | 收入层启动阈值（默认 100000） |
| `QQQI_INCOME_RATIO` | QQQI 在收入层中的占比，0–1（默认 0.5） |
| `NOTIFY_LANG` | 通知语言: `en`（英文，默认）或 `zh`（中文） |

部署为 Cloud Run 服务，定时触发根 URL（如每交易日一次）。入口：`main.py` 中的 Flask 路由 `"/"`。
