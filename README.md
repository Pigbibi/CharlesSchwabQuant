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

This repository uses `QuantPlatformKit` for Schwab client bootstrap, account snapshot access, market data, and order submission. Cloud Run deploys this repository directly.
The `hybrid_growth_income` strategy implementation is sourced from `UsEquityStrategies`.

Full strategy documentation now lives in [`UsEquityStrategies`](https://github.com/QuantStrategyLab/UsEquityStrategies#hybrid_growth_income). The sections below focus on execution-side defaults and runtime behavior.
This runtime matrix is the authoritative enablement source for Schwab. `UsEquityStrategies` only carries strategy-layer compatibility and metadata.

### Execution boundary

The mainline runtime now follows one path only:

- `main.py` assembles `StrategyContext` plus platform overrides
- `strategy_runtime.py` loads the unified strategy entrypoint
- `entrypoint.evaluate(ctx)` returns a shared `StrategyDecision`
- `decision_mapper.py` converts that decision into Schwab orders, notifications, and runtime updates

Platform execution no longer depends on `strategy/allocation.py`, hard-coded strategy symbol lists, or direct reads of strategy-private config constants.


**Schwab profile matrix**

| Canonical profile | Display name | Enabled | Default | Rollback | Domain | Runtime note |
| --- | --- | --- | --- | --- | --- | --- |
| `hybrid_growth_income` | QQQ/TQQQ Growth Income | Yes | Yes | Yes | `us_equity` | current Schwab default |

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

Telegram notifications include structured execution and heartbeat messages, with English and Chinese variants.

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
| `SCHWAB_API_KEY` | Schwab API key; recommended to inject from Secret Manager secret `charles-schwab-api-key` |
| `SCHWAB_APP_SECRET` | Schwab API secret; recommended to inject from Secret Manager secret `charles-schwab-app-secret` |
| `TELEGRAM_TOKEN` | Telegram bot token; recommended to inject from Secret Manager secret `charles-schwab-telegram-token` |
| `GLOBAL_TELEGRAM_CHAT_ID` | Telegram chat ID used by this service. |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID |
| `STRATEGY_PROFILE` | Strategy profile selector (default: `hybrid_growth_income`; runtime value: `hybrid_growth_income`) |
| `INCOME_THRESHOLD_USD` | Equity threshold to enable income layer (default 100000) |
| `QQQI_INCOME_RATIO` | QQQI share of income layer, 0–1 (default 0.5) |
| `NOTIFY_LANG` | Notification language: `en` (English, default) or `zh` (Chinese) |

Only `GLOBAL_TELEGRAM_CHAT_ID` and `NOTIFY_LANG` are good candidates for cross-project sharing. `TELEGRAM_TOKEN`, Schwab API credentials, and other runtime secrets should remain repository-specific.

The Schwab OAuth token payload is read from Secret Manager secret `schwab_token`.

Recommended Secret Manager runtime secrets in the `charlesschwabquant` project:

- `schwab_token`
- `charles-schwab-api-key`
- `charles-schwab-app-secret`
- `charles-schwab-telegram-token`

### GitHub-managed Cloud Run env sync

If code deployment still uses Google Cloud Trigger, but you want GitHub to be the single source of truth for runtime env vars, this repo now includes `.github/workflows/sync-cloud-run-env.yml`.

Recommended setup:

- **Repository Variables**
  - `ENABLE_GITHUB_ENV_SYNC` = `true`
  - `CLOUD_RUN_REGION`
  - `CLOUD_RUN_SERVICE`
  - `TELEGRAM_TOKEN_SECRET_NAME` (recommended: `charles-schwab-telegram-token`)
  - `SCHWAB_API_KEY_SECRET_NAME` (recommended: `charles-schwab-api-key`)
  - `SCHWAB_APP_SECRET_SECRET_NAME` (recommended: `charles-schwab-app-secret`)
  - Optional: `STRATEGY_PROFILE` (recommended: `hybrid_growth_income`)
  - Optional: `INCOME_THRESHOLD_USD`
  - Optional: `QQQI_INCOME_RATIO`
  - Optional: `GOOGLE_CLOUD_PROJECT`
- **Repository Secrets**
  - Optional fallback only: `TELEGRAM_TOKEN`
  - Optional fallback only: `SCHWAB_API_KEY`
  - Optional fallback only: `SCHWAB_APP_SECRET`
- **Shared Variables already supported**
  - `GLOBAL_TELEGRAM_CHAT_ID`
  - `NOTIFY_LANG`

On every push to `main`, the workflow updates the existing Cloud Run service with the values above and removes `TELEGRAM_CHAT_ID`.

Important:

- The workflow only becomes strict when `ENABLE_GITHUB_ENV_SYNC=true`. If this variable is unset, the sync job is skipped and the old Google Cloud Trigger + manual Cloud Run env setup keeps working.
- `STRATEGY_PROFILE` is kept as the future strategy-switch entry. Today this service only enables `hybrid_growth_income`.
- The current strategy domain is `us_equity`, and the repo now keeps a thin strategy registry so future expansion can grow by domain + profile instead of mixing strategy and platform in one layer.
- `INCOME_THRESHOLD_USD` and `QQQI_INCOME_RATIO` are optional in env sync. If you leave them unset, the app keeps using the code defaults (`100000` and `0.5`).
- GitHub now authenticates to Google Cloud with OIDC + Workload Identity Federation. `GCP_SA_KEY` is no longer required for this workflow.
- The Telegram token and Schwab API credentials should live in Secret Manager and be referenced by the secret-name variables above. Across multiple quant repos, only `GLOBAL_TELEGRAM_CHAT_ID` and `NOTIFY_LANG` are good cross-project shared settings.

### Deployment unit and naming

- `QuantPlatformKit` is only a shared dependency; Cloud Run still deploys `CharlesSchwabPlatform` itself.
- Recommended Cloud Run service name: `charles-schwab-quant-hybrid-growth-income-service`.
- If you later rename or move this repository, reselect the GitHub source in Cloud Build / Cloud Run trigger instead of assuming the previous source binding will follow the rename.
- For the shared deployment model and trigger migration checklist, see [`QuantPlatformKit/docs/deployment_model.md`](../QuantPlatformKit/docs/deployment_model.md).

Deploy as a Cloud Run service and trigger the root URL on a schedule (e.g. once per trading day). Entry point: Flask route `"/"` in `main.py`.

---

<a id="中文"></a>
## 中文

基于 Charles Schwab 账户的自动化交易服务，部署在 GCP Cloud Run 上。资金分配为三层：**进攻层 (TQQQ)** 基于 QQQ MA200 + ATR 波段分阶段退出，**收入层 (SPYI / QQQI)** 在资产超过阈值时启用，**防御层 (BOXX)** 管理闲置资金。每次运行获取数据、计算目标、下单并通过 Telegram 通知。

这个仓库通过 `QuantPlatformKit` 复用 Schwab client 初始化、账户快照、行情读取和下单逻辑。Cloud Run 直接部署这个仓库。
`hybrid_growth_income` 策略实现来自 `UsEquityStrategies`。

完整策略说明现在放在 [`UsEquityStrategies`](https://github.com/QuantStrategyLab/UsEquityStrategies#hybrid_growth_income)。下面这些章节主要保留执行侧默认值和运行时行为。

### 执行边界

当前主线运行路径已经统一为：

- `main.py` 负责组装 `StrategyContext` 和平台 override
- `strategy_runtime.py` 负责加载统一策略入口
- `entrypoint.evaluate(ctx)` 返回共享的 `StrategyDecision`
- `decision_mapper.py` 再把决策转换成 Schwab 订单、通知和运行时更新

平台执行主线已经不再依赖 `strategy/allocation.py`、硬编码策略符号列表，也不再直接读取策略私有配置常量。

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

Telegram 通知包含结构化的调仓和心跳消息，支持中英文切换。

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
| `SCHWAB_API_KEY` | Schwab API 密钥；建议通过 Secret Manager 的 `charles-schwab-api-key` 注入 |
| `SCHWAB_APP_SECRET` | Schwab API 密钥；建议通过 Secret Manager 的 `charles-schwab-app-secret` 注入 |
| `TELEGRAM_TOKEN` | Telegram 机器人 Token；建议通过 Secret Manager 的 `charles-schwab-telegram-token` 注入 |
| `GLOBAL_TELEGRAM_CHAT_ID` | 这个服务使用的 Telegram Chat ID。 |
| `GOOGLE_CLOUD_PROJECT` | GCP 项目 ID |
| `STRATEGY_PROFILE` | 策略档位选择（默认: `hybrid_growth_income`；运行时直接用 `hybrid_growth_income`） |
| `INCOME_THRESHOLD_USD` | 收入层启动阈值（默认 100000） |
| `QQQI_INCOME_RATIO` | QQQI 在收入层中的占比，0–1（默认 0.5） |
| `NOTIFY_LANG` | 通知语言: `en`（英文，默认）或 `zh`（中文） |

如果你在多个 quant 仓库之间保留一层共享配置，通常只建议共享 `GLOBAL_TELEGRAM_CHAT_ID` 和 `NOTIFY_LANG`。`TELEGRAM_TOKEN`、Schwab API key 这些仍然应该由这个仓库自己管理。

Schwab OAuth token payload 当前从 Secret Manager 的 `schwab_token` 里读取。

建议在 `charlesschwabquant` 项目里同时维护这些运行时 secret：

- `schwab_token`
- `charles-schwab-api-key`
- `charles-schwab-app-secret`
- `charles-schwab-telegram-token`

### GitHub 统一管理 Cloud Run 环境变量

如果代码部署继续走 Google Cloud Trigger，但你想把运行时环境变量统一放在 GitHub 管理，这个仓库现在提供了 `.github/workflows/sync-cloud-run-env.yml`。

推荐配置方式：

- **仓库级 Variables**
  - `ENABLE_GITHUB_ENV_SYNC` = `true`
  - `CLOUD_RUN_REGION`
  - `CLOUD_RUN_SERVICE`
  - `TELEGRAM_TOKEN_SECRET_NAME`（建议：`charles-schwab-telegram-token`）
  - `SCHWAB_API_KEY_SECRET_NAME`（建议：`charles-schwab-api-key`）
  - `SCHWAB_APP_SECRET_SECRET_NAME`（建议：`charles-schwab-app-secret`）
  - 可选：`STRATEGY_PROFILE`（建议设为 `hybrid_growth_income`）
  - 可选：`INCOME_THRESHOLD_USD`
  - 可选：`QQQI_INCOME_RATIO`
  - 可选：`GOOGLE_CLOUD_PROJECT`
- **仓库级 Secrets**
  - 仅保留为 fallback：`TELEGRAM_TOKEN`
  - 仅保留为 fallback：`SCHWAB_API_KEY`
  - 仅保留为 fallback：`SCHWAB_APP_SECRET`
- **已支持的共享 Variables**
  - `GLOBAL_TELEGRAM_CHAT_ID`
  - `NOTIFY_LANG`

每次 push 到 `main` 时，这个 workflow 会把上面这些值同步到现有 Cloud Run 服务里，并删除旧的 `TELEGRAM_CHAT_ID`。

注意：

- 只有在 `ENABLE_GITHUB_ENV_SYNC=true` 时，这个 workflow 才会严格校验并执行同步。没打开时会直接跳过，不影响原来 Google Cloud Trigger + 手工 Cloud Run env 的老流程。
- `STRATEGY_PROFILE` 当前只启用 `hybrid_growth_income`。
- 当前策略域是 `us_equity`，本地策略注册表只用于域和 profile 校验。
- `INCOME_THRESHOLD_USD` 和 `QQQI_INCOME_RATIO` 在 env-sync 里是可选项。不填时，程序会继续使用代码里的默认值：`100000` 和 `0.5`。
- GitHub 现在通过 OIDC + Workload Identity Federation 登录 Google Cloud，这个 workflow 不再需要 `GCP_SA_KEY`。
- Telegram token 和 Schwab API 凭据建议放到 Secret Manager，并通过上面的 secret-name 变量引用。对多个 quant 仓库来说，真正适合跨项目共享的通常只有 `GLOBAL_TELEGRAM_CHAT_ID` 和 `NOTIFY_LANG`。

### 部署单元和命名建议

- `QuantPlatformKit` 只是共享依赖，不单独部署；Cloud Run 继续只部署 `CharlesSchwabPlatform`。
- 推荐 Cloud Run 服务名：`charles-schwab-quant-hybrid-growth-income-service`。
- 如果后面改 GitHub 仓库名或再次迁组织，Cloud Build / Cloud Run 里的 GitHub 来源需要重新选择，不要假设旧绑定会自动跟过去。
- 统一部署模型和触发器迁移清单见 [`QuantPlatformKit/docs/deployment_model.md`](../QuantPlatformKit/docs/deployment_model.md)。

部署为 Cloud Run 服务，定时触发根 URL（如每交易日一次）。入口：`main.py` 中的 Flask 路由 `"/"`。
