# Schwab Trinity Strategy Bot

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Platform](https://img.shields.io/badge/Broker-Charles%20Schwab-00a0df)
![Strategy](https://img.shields.io/badge/Strategy-Trinity%20Hybrid-orange)
![GCP](https://img.shields.io/badge/GCP-Cloud%20Run-4285F4)

[English](#english) | [中文](#中文)

---

<a id="english"></a>
## English

Automated trading service for Charles Schwab accounts, deployed on GCP Cloud Run. This repository runs shared `us_equity` strategy profiles from `UsEquityStrategies`; strategy logic, cadence, asset universes, parameters, and research/backtest notes live in that strategy repository.

This repository uses `QuantPlatformKit` for Schwab client bootstrap, account snapshot access, market data, and order submission. Cloud Run deploys this repository directly.
The Schwab runtime can execute the six current `runtime_enabled` `us_equity` profiles from `UsEquityStrategies`.

Full strategy documentation now lives in [`UsEquityStrategies`](https://github.com/QuantStrategyLab/UsEquityStrategies). The sections below focus on Schwab runtime behavior, profile enablement, deployment, and credentials.
This runtime matrix is the authoritative enablement source for Schwab. `UsEquityStrategies` carries strategy-layer logic, cadence, compatibility, and metadata.

### Execution boundary

The mainline runtime now follows one path only:

- `main.py` assembles `StrategyContext` plus platform overrides
- `strategy_runtime.py` loads the unified strategy entrypoint
- `entrypoint.evaluate(ctx)` returns a shared `StrategyDecision`
- `decision_mapper.py` converts that decision into Schwab orders, notifications, and runtime updates

Platform execution no longer depends on `strategy/allocation.py`, hard-coded strategy symbol lists, or direct reads of strategy-private config constants.


**Schwab profile status**

| Canonical profile | Display name | Eligible | Enabled | Domain | Runtime note |
| --- | --- | --- | --- | --- | --- |
| `global_etf_rotation` | Global ETF Rotation | Yes | Yes | `us_equity` | enabled weight-mode rotation line |
| `russell_1000_multi_factor_defensive` | Russell 1000 Multi-Factor | Yes | Yes | `us_equity` | enabled feature-snapshot stock baseline |
| `mega_cap_leader_rotation_top50_balanced` | Mega Cap Leader Rotation Top50 Balanced | Yes | Yes | `us_equity` | selectable balanced Top50 monthly leader rotation |
| `tqqq_growth_income` | TQQQ Growth Income | Yes | Yes | `us_equity` | selectable growth line |
| `soxl_soxx_trend_income` | SOXL/SOXX Semiconductor Trend Income | Yes | Yes | `us_equity` | enabled value-mode alternative |
| `tech_communication_pullback_enhancement` | Tech/Communication Pullback Enhancement | Yes | Yes | `us_equity` | enabled feature-snapshot tech branch |
| `mega_cap_leader_rotation_aggressive` | Mega Cap Leader Rotation Aggressive | Yes | No | `us_equity` | research-only archive |
| `mega_cap_leader_rotation_dynamic_top20` | Mega Cap Leader Rotation Dynamic Top20 | Yes | No | `us_equity` | research-only archive |
| `dynamic_mega_leveraged_pullback` | Dynamic Mega Leveraged Pullback | Yes | No | `us_equity` | research-only archive |

Check the current matrix locally:

```bash
python3 scripts/print_strategy_profile_status.py
```

### Strategy documentation boundary

Strategy logic, cadence, asset universes, parameters, and research/backtest notes live in `UsEquityStrategies`. This platform README keeps only Schwab profile enablement, env vars, deployment wiring, broker execution behavior, and notification transport.

### Notifications and orders

Telegram notifications include structured execution and heartbeat messages, with English and Chinese variants. Strategy-specific signal/status fields come from the selected `UsEquityStrategies` profile; Schwab-specific handling covers account snapshot access, order submission, and runtime error reporting.

Each HTTP request runs one broker execution cycle. The Cloud Scheduler cron should follow the strategy-layer cadence in `UsEquityStrategies`.

### Environment variables

| Variable | Description |
|----------|-------------|
| `SCHWAB_API_KEY` | Schwab API key; recommended to inject from Secret Manager secret `charles-schwab-api-key` |
| `SCHWAB_APP_SECRET` | Schwab API secret; recommended to inject from Secret Manager secret `charles-schwab-app-secret` |
| `TELEGRAM_TOKEN` | Telegram bot token; recommended to inject from Secret Manager secret `charles-schwab-telegram-token` |
| `GLOBAL_TELEGRAM_CHAT_ID` | Telegram chat ID used by this service. |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID |
| `STRATEGY_PROFILE` | Strategy profile selector. Set explicitly per deployment; current enabled values include `global_etf_rotation`, `mega_cap_leader_rotation_top50_balanced`, `russell_1000_multi_factor_defensive`, `tqqq_growth_income`, `soxl_soxx_trend_income`, and `tech_communication_pullback_enhancement` |
| `SCHWAB_STRATEGY_PLUGIN_MOUNTS_JSON` | Optional Schwab-side strategy plugin mount JSON. Prefer this Schwab-specific variable; `STRATEGY_PLUGIN_MOUNTS_JSON` is only a shared fallback. |
| `SCHWAB_MIN_RESERVED_CASH_USD` | Optional platform cash-reserve floor in USD. Default: `150`. The runtime keeps at least `max(floor, ratio * total_equity)`. |
| `SCHWAB_RESERVED_CASH_RATIO` | Optional platform cash-reserve ratio. Default: `0.03`. The runtime keeps at least `max(floor, ratio * total_equity)`. |
| `INCOME_THRESHOLD_USD` | Optional override for the strategy income-layer threshold. Leave unset to use the `UsEquityStrategies` live default, which disables the income layer for normal account sizes. |
| `QQQI_INCOME_RATIO` | Optional override for QQQI share of the income layer, 0–1. Only relevant when the income layer is enabled. |
| `DUAL_DRIVE_UNLEVERED_SYMBOL` | Optional `tqqq_growth_income` override for the tradable unlevered growth sleeve. Leave unset for `QQQ`; set to `QQQM` for smaller Schwab accounts while retaining `QQQ` as the signal source. |
| `NOTIFY_LANG` | Notification language: `en` (English, default) or `zh` (Chinese) |

Strategy plugin mount JSON belongs to platform/deployment configuration, not strategy code. It decides which plugin artifacts this runtime reads, and must not set `mode`; the plugin artifact is self-identifying and carries the effective mode. Invalid plugin mount config is recorded in the runtime report diagnostics and does not block the base strategy cycle.

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
  - `STRATEGY_PROFILE` (set explicitly to one enabled profile: `global_etf_rotation`, `mega_cap_leader_rotation_top50_balanced`, `russell_1000_multi_factor_defensive`, `tqqq_growth_income`, `soxl_soxx_trend_income`, or `tech_communication_pullback_enhancement`)
  - Optional: `SCHWAB_FEATURE_SNAPSHOT_PATH`, `SCHWAB_FEATURE_SNAPSHOT_MANIFEST_PATH`, `SCHWAB_STRATEGY_CONFIG_PATH` for feature-snapshot profiles
  - Optional: `SCHWAB_STRATEGY_PLUGIN_MOUNTS_JSON` for strategy plugin artifact mounts. Do not include `mode` in this platform mount JSON.
  - Optional: `INCOME_THRESHOLD_USD`
  - Optional: `QQQI_INCOME_RATIO`
  - Optional: `DUAL_DRIVE_UNLEVERED_SYMBOL`
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

- The workflow only becomes strict when `ENABLE_GITHUB_ENV_SYNC=true`. If this variable is unset, the sync job is skipped and the old Google Cloud Trigger + manual Cloud Run env setup keeps working. When enabled, it resolves the selected profile's snapshot/config requirements from `scripts/print_strategy_profile_status.py --json` instead of a hard-coded strategy-name list.
- `STRATEGY_PROFILE` is driven by the platform capability matrix plus a rollout allowlist derived from `runtime_enabled` strategy metadata. Today `enabled` includes six live `us_equity` profiles: `global_etf_rotation`, `mega_cap_leader_rotation_top50_balanced`, `russell_1000_multi_factor_defensive`, `tqqq_growth_income`, `soxl_soxx_trend_income`, and `tech_communication_pullback_enhancement`; archived research-only profiles remain eligible in the capability matrix but are not enabled.
- The current strategy domain is `us_equity`, and the repo now keeps a thin strategy registry so future expansion can grow by domain + profile instead of mixing strategy and platform in one layer.
- `INCOME_THRESHOLD_USD`, `QQQI_INCOME_RATIO`, and `DUAL_DRIVE_UNLEVERED_SYMBOL` are optional in env sync. Leave them unset to inherit the `UsEquityStrategies` profile defaults; the current `tqqq_growth_income` live default is the no-income QQQ/TQQQ dual-drive mode. Set `DUAL_DRIVE_UNLEVERED_SYMBOL=QQQM` when the Schwab account should trade QQQM instead of whole-share QQQ.
- GitHub now authenticates to Google Cloud with OIDC + Workload Identity Federation. `GCP_SA_KEY` is no longer required for this workflow.
- If you deploy with `gcloud run deploy --source` or a Cloud Run source trigger, also grant `roles/storage.objectViewer` on `gs://run-sources-<project>-<region>` to the build service account, the deploy service account, and the default compute service account. Without that bucket access, source deploy fails before Cloud Build starts with `storage.objects.get` denied.
- The Telegram token and Schwab API credentials should live in Secret Manager and be referenced by the secret-name variables above. Across multiple quant repos, only `GLOBAL_TELEGRAM_CHAT_ID` and `NOTIFY_LANG` are good cross-project shared settings.

### Deployment unit and naming

- `QuantPlatformKit` is only a shared dependency; Cloud Run still deploys `CharlesSchwabPlatform` itself.
- Recommended Cloud Run service name: `charles-schwab-quant-service`.
- If you later rename or move this repository, reselect the GitHub source in Cloud Build / Cloud Run trigger instead of assuming the previous source binding will follow the rename.
- For the shared deployment model and trigger migration checklist, see [`QuantPlatformKit/docs/deployment_model.md`](../QuantPlatformKit/docs/deployment_model.md).

Deploy as a Cloud Run service and trigger the root URL on a schedule chosen from the strategy-layer cadence in `UsEquityStrategies`. Entry point: Flask route `"/"` in `main.py`.

---

<a id="中文"></a>
## 中文

基于 Charles Schwab 账户的自动化交易服务，部署在 GCP Cloud Run 上。这个仓库负责运行 `UsEquityStrategies` 里的共享 `us_equity` 策略档位；策略逻辑、策略频率、标的池、参数和研究/回测说明都放在策略仓库。

这个仓库通过 `QuantPlatformKit` 复用 Schwab client 初始化、账户快照、行情读取和下单逻辑。Cloud Run 直接部署这个仓库。
Schwab runtime 现在可以直接执行 `UsEquityStrategies` 里的 6 条 `runtime_enabled` `us_equity` 策略：`global_etf_rotation`、`mega_cap_leader_rotation_top50_balanced`、`russell_1000_multi_factor_defensive`、`tqqq_growth_income`、`soxl_soxx_trend_income` 和 `tech_communication_pullback_enhancement`；`dynamic_mega_leveraged_pullback`、`mega_cap_leader_rotation_aggressive`、`mega_cap_leader_rotation_dynamic_top20` 保留为 research-only 存档，不进入 Schwab rollout。

完整策略说明现在放在 [`UsEquityStrategies`](https://github.com/QuantStrategyLab/UsEquityStrategies)。下面这些章节只保留 Schwab 运行时、profile 启用状态、部署和凭据说明。

### 执行边界

当前主线运行路径已经统一为：

- `main.py` 负责组装 `StrategyContext` 和平台 override
- `strategy_runtime.py` 负责加载统一策略入口
- `entrypoint.evaluate(ctx)` 返回共享的 `StrategyDecision`
- `decision_mapper.py` 再把决策转换成 Schwab 订单、通知和运行时更新

平台执行主线已经不再依赖 `strategy/allocation.py`、硬编码策略符号列表，也不再直接读取策略私有配置常量。

### 策略文档边界

策略逻辑、策略频率、标的池、参数和研究/回测说明都放在 `UsEquityStrategies`。这个平台 README 只保留 Schwab profile 启用状态、环境变量、部署 wiring、券商执行行为和通知通道说明。

### 通知和订单

Telegram 通知包含结构化的调仓和心跳消息，支持中英文切换。策略相关的信号/状态字段来自当前选择的 `UsEquityStrategies` profile；Schwab 侧负责账户快照、下单和运行时异常处理。

每个 HTTP 请求执行一次券商运行周期。Cloud Scheduler 的 cron 应以 `UsEquityStrategies` 里的策略层频率为准。

### 环境变量

| 变量 | 说明 |
|------|------|
| `SCHWAB_API_KEY` | Schwab API 密钥；建议通过 Secret Manager 的 `charles-schwab-api-key` 注入 |
| `SCHWAB_APP_SECRET` | Schwab API 密钥；建议通过 Secret Manager 的 `charles-schwab-app-secret` 注入 |
| `TELEGRAM_TOKEN` | Telegram 机器人 Token；建议通过 Secret Manager 的 `charles-schwab-telegram-token` 注入 |
| `GLOBAL_TELEGRAM_CHAT_ID` | 这个服务使用的 Telegram Chat ID。 |
| `GOOGLE_CLOUD_PROJECT` | GCP 项目 ID |
| `STRATEGY_PROFILE` | 策略档位选择。每个部署都要显式设置；当前已启用值包括 `global_etf_rotation`、`mega_cap_leader_rotation_top50_balanced`、`russell_1000_multi_factor_defensive`、`tqqq_growth_income`、`soxl_soxx_trend_income` 和 `tech_communication_pullback_enhancement` |
| `SCHWAB_STRATEGY_PLUGIN_MOUNTS_JSON` | 可选的 Schwab 侧策略插件挂载 JSON。优先使用这个 Schwab 专用变量；`STRATEGY_PLUGIN_MOUNTS_JSON` 只作为共享 fallback。 |
| `SCHWAB_MIN_RESERVED_CASH_USD` | 可选的平台保留现金下限，单位 USD。默认 `150`。实际保留现金取 `max(下限, 比例 * 总资产)`。 |
| `SCHWAB_RESERVED_CASH_RATIO` | 可选的平台保留现金比例。默认 `0.03`。实际保留现金取 `max(下限, 比例 * 总资产)`。 |
| `INCOME_THRESHOLD_USD` | 可选的收入层启动阈值覆盖。不填时使用 `UsEquityStrategies` 的实盘默认值，也就是普通账户规模下关闭收入层。 |
| `QQQI_INCOME_RATIO` | 可选的 QQQI 收入层占比覆盖，0–1。只有启用收入层时才有意义。 |
| `DUAL_DRIVE_UNLEVERED_SYMBOL` | 可选的 `tqqq_growth_income` 非杠杆增长袖子交易标的覆盖。不填时使用 `QQQ`；小账户可以设置为 `QQQM`，但主信号仍使用 `QQQ`。 |
| `NOTIFY_LANG` | 通知语言: `en`（英文，默认）或 `zh`（中文） |

策略插件挂载 JSON 属于平台/部署配置，不属于策略代码。它只决定当前 runtime 读取哪些插件 artifact，不能在挂载里设置 `mode`；插件 artifact 自带身份和有效 mode。插件挂载配置错误会写入 runtime report diagnostics，不阻断基础策略运行周期。

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
  - `STRATEGY_PROFILE`（显式设置为任一已启用 profile：`global_etf_rotation`、`mega_cap_leader_rotation_top50_balanced`、`russell_1000_multi_factor_defensive`、`tqqq_growth_income`、`soxl_soxx_trend_income` 或 `tech_communication_pullback_enhancement`）
  - 可选：`SCHWAB_FEATURE_SNAPSHOT_PATH`、`SCHWAB_FEATURE_SNAPSHOT_MANIFEST_PATH`、`SCHWAB_STRATEGY_CONFIG_PATH`，用于 feature-snapshot 策略
  - 可选：`SCHWAB_STRATEGY_PLUGIN_MOUNTS_JSON`，用于策略插件 artifact 挂载。不要在这个平台挂载 JSON 里放 `mode`
  - 可选：`INCOME_THRESHOLD_USD`
  - 可选：`QQQI_INCOME_RATIO`
  - 可选：`DUAL_DRIVE_UNLEVERED_SYMBOL`
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

- 只有在 `ENABLE_GITHUB_ENV_SYNC=true` 时，这个 workflow 才会严格校验并执行同步。没打开时会直接跳过，不影响原来 Google Cloud Trigger + 手工 Cloud Run env 的老流程。打开后，它会通过 `scripts/print_strategy_profile_status.py --json` 动态解析目标策略需要的 snapshot/config 输入，不再维护硬编码策略名列表。
- `STRATEGY_PROFILE` 现在由平台能力矩阵和从 `runtime_enabled` 策略元数据派生的 rollout allowlist 一起决定。当前 `enabled` 包含 6 条 live `us_equity` 策略：`global_etf_rotation`、`mega_cap_leader_rotation_top50_balanced`、`russell_1000_multi_factor_defensive`、`tqqq_growth_income`、`soxl_soxx_trend_income` 和 `tech_communication_pullback_enhancement`；research-only 存档 profile 仍保留能力矩阵兼容性，但不会启用。
- 当前策略域是 `us_equity`，本地策略注册表只用于域和 profile 校验。
- `INCOME_THRESHOLD_USD`、`QQQI_INCOME_RATIO` 和 `DUAL_DRIVE_UNLEVERED_SYMBOL` 在 env-sync 里是可选项。不填时会继承 `UsEquityStrategies` 的 profile 默认值；当前 `tqqq_growth_income` 实盘默认是不带收入层的 QQQ/TQQQ 双轮模式。Schwab 小账户需要用 QQQM 替代整股 QQQ 时，设置 `DUAL_DRIVE_UNLEVERED_SYMBOL=QQQM`。
- GitHub 现在通过 OIDC + Workload Identity Federation 登录 Google Cloud，这个 workflow 不再需要 `GCP_SA_KEY`。
- 如果你用 `gcloud run deploy --source` 或 Cloud Run source trigger 部署，还要确保 `gs://run-sources-<project>-<region>` 这个 staging bucket 给 build service account、deploy service account、默认 compute service account 都加上 `roles/storage.objectViewer`。少了这层权限，会在 Cloud Build 启动前直接报 `storage.objects.get denied`。
- Telegram token 和 Schwab API 凭据建议放到 Secret Manager，并通过上面的 secret-name 变量引用。对多个 quant 仓库来说，真正适合跨项目共享的通常只有 `GLOBAL_TELEGRAM_CHAT_ID` 和 `NOTIFY_LANG`。

### 部署单元和命名建议

- `QuantPlatformKit` 只是共享依赖，不单独部署；Cloud Run 继续只部署 `CharlesSchwabPlatform`。
- 推荐 Cloud Run 服务名：`charles-schwab-quant-service`。
- 如果后面改 GitHub 仓库名或再次迁组织，Cloud Build / Cloud Run 里的 GitHub 来源需要重新选择，不要假设旧绑定会自动跟过去。
- 统一部署模型和触发器迁移清单见 [`QuantPlatformKit/docs/deployment_model.md`](../QuantPlatformKit/docs/deployment_model.md)。

部署为 Cloud Run 服务，定时触发根 URL（如每交易日一次）。入口：`main.py` 中的 Flask 路由 `"/"`。
