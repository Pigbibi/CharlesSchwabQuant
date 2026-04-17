"""Telegram notification and i18n helpers for CharlesSchwabPlatform."""

from __future__ import annotations

import requests


SIGNAL_ICONS = {
    "hold": "💎",
    "entry": "🚀",
    "reduce": "⚠️",
    "exit": "🔴",
    "idle": "💤",
}


I18N = {
    "zh": {
        "trade_header": "🔔 【交易执行报告】",
        "heartbeat_header": "💓 【心跳检测】",
        "error_header": "🚨 【策略异常】",
        "strategy_label": "🧭 策略: {name}",
        "signal_label": "信号",
        "dry_run_banner": "🧪 模拟运行，本轮不提交真实订单",
        "dashboard_label": "📊 资产看板",
        "holdings_title": "💼 持仓",
        "benchmark_title": "📈 {symbol} 基准",
        "benchmark_price": "{symbol}: {value}",
        "benchmark_ma200": "MA200: {value}",
        "benchmark_exit": "退出线: {value}",
        "equity": "净值",
        "buying_power": "购买力",
        "no_trades": "✅ 无需调仓",
        "separator": "━━━━━━━━━━━━━━━━━━",
        "signal_hold": "趋势持有",
        "signal_entry": "入场信号",
        "signal_reduce": "减仓信号",
        "signal_exit": "离场信号",
        "signal_idle": "等待信号",
        "market_status_risk_on": "🚀 风险开启（{asset}）",
        "market_status_delever": "🛡️ 降杠杆（{asset}）",
        "signal_risk_on": "SOXL 站上 {window} 日均线，持有 SOXL，交易层风险仓位 {ratio}",
        "signal_delever": "SOXL 跌破 {window} 日均线，切换至 SOXX，交易层风险仓位 {ratio}",
        "market_status_blend_gate_risk_on": "🚀 风险开启（{asset}）",
        "market_status_blend_gate_defensive": "🛡️ 降杠杆（{asset}）",
        "signal_blend_gate_risk_on": "{trend_symbol} 站上 {window} 日门槛线，持有 SOXL {soxl_ratio} + SOXX {soxx_ratio}",
        "signal_blend_gate_defensive": "{trend_symbol} 跌破门槛线，防守持有 SOXX {soxx_ratio}",
        "limit_buy": "限价买入",
        "market_buy": "市价买入",
        "market_sell": "市价卖出",
        "shares": "股",
        "submitted": "已下发",
        "failed": "失败",
        "exception": "异常",
        "buy_label": "买入",
        "limit_buy_cmd": "限价买入指令",
        "market_buy_cmd": "市价买入指令",
        "market_sell_cmd": "市价卖出指令",
        "dry_run_trade_log": "🧪 模拟下单：{command} {symbol}: {quantity}{shares}",
        "dry_run_trade_log_with_price": "🧪 模拟下单：{command} {symbol} (${price}): {quantity}{shares}",
        "post_sell_buying_power_unreleased": "ℹ️ 卖出后购买力未释放，本轮跳过买入，等待下次执行",
        "order_id_suffix": "（订单号: {order_id}）",
        "small_account_warning_note": "小账户提示：净值 {portfolio_equity} 低于建议 {min_recommended_equity}；{reason}",
        "small_account_warning_reason_integer_shares_min_position_value_may_prevent_backtest_replication": "整数股和最小仓位限制可能导致实盘无法完全复现回测",
        "strategy_plugin_line": "🧩 插件：{plugin} | 模式：{mode} | 路由：{route} | 建议：{action}",
        "strategy_plugin_name_crisis_response_shadow": "危机响应观察",
        "strategy_plugin_mode_shadow": "影子观察",
        "strategy_plugin_mode_paper": "模拟账本",
        "strategy_plugin_mode_advisory": "人工确认建议",
        "strategy_plugin_mode_live": "实盘插件",
        "strategy_plugin_route_no_action": "不操作",
        "strategy_plugin_route_true_crisis": "真危机",
        "strategy_plugin_route_taco_fake_crisis": "TACO 假危机",
        "strategy_plugin_route_unknown_route": "未知路由",
        "strategy_plugin_action_no_action": "不操作",
        "strategy_plugin_action_watch_only": "仅观察",
        "strategy_plugin_action_small_taco": "小仓 TACO",
        "strategy_plugin_action_defend": "防守",
        "strategy_plugin_action_blocked": "已阻断",
        "strategy_plugin_action_monitor": "监控",
        "strategy_plugin_action_unknown_action": "未知建议",
        "strategy_name_tqqq_growth_income": "TQQQ 增长收益",
        "strategy_name_soxl_soxx_trend_income": "SOXL/SOXX 半导体趋势收益",
        "strategy_name_global_etf_rotation": "全球 ETF 轮动",
        "strategy_name_russell_1000_multi_factor_defensive": "罗素1000多因子",
        "strategy_name_tech_communication_pullback_enhancement": "科技通信回调增强",
        "strategy_name_qqq_tech_enhancement": "科技通信回调增强",
        "strategy_name_mega_cap_leader_rotation_aggressive": "Mega Cap 激进龙头轮动",
        "strategy_name_mega_cap_leader_rotation_dynamic_top20": "Mega Cap 动态 Top20 龙头轮动",
        "strategy_name_mega_cap_leader_rotation_top50_balanced": "Mega Cap Top50 平衡龙头轮动",
        "strategy_name_dynamic_mega_leveraged_pullback": "Mega Cap 2x 回调策略",
    },
    "en": {
        "trade_header": "🔔 【Trade Execution Report】",
        "heartbeat_header": "💓 【Heartbeat】",
        "error_header": "🚨 【Strategy Error】",
        "strategy_label": "🧭 Strategy: {name}",
        "signal_label": "Signal",
        "dry_run_banner": "🧪 Dry run only; no live orders submitted",
        "dashboard_label": "📊 Dashboard",
        "holdings_title": "💼 Holdings",
        "benchmark_title": "📈 {symbol} Benchmark",
        "benchmark_price": "{symbol}: {value}",
        "benchmark_ma200": "MA200: {value}",
        "benchmark_exit": "Exit: {value}",
        "equity": "Equity",
        "buying_power": "Buying Power",
        "no_trades": "✅ No rebalance needed",
        "separator": "━━━━━━━━━━━━━━━━━━",
        "signal_hold": "Trend Hold",
        "signal_entry": "Entry Signal",
        "signal_reduce": "Reduce Signal",
        "signal_exit": "Exit Signal",
        "signal_idle": "Idle",
        "market_status_risk_on": "🚀 RISK-ON ({asset})",
        "market_status_delever": "🛡️ DE-LEVER ({asset})",
        "signal_risk_on": "SOXL above {window}d MA, hold SOXL, risk {ratio}",
        "signal_delever": "SOXL below {window}d MA, switch to SOXX, risk {ratio}",
        "market_status_blend_gate_risk_on": "🚀 RISK-ON ({asset})",
        "market_status_blend_gate_defensive": "🛡️ DE-LEVER ({asset})",
        "signal_blend_gate_risk_on": "{trend_symbol} above {window}d gated entry, hold SOXL {soxl_ratio} + SOXX {soxx_ratio}",
        "signal_blend_gate_defensive": "{trend_symbol} below gated entry, hold defensive SOXX {soxx_ratio}",
        "limit_buy": "Limit Buy",
        "market_buy": "Market Buy",
        "market_sell": "Market Sell",
        "shares": " shares",
        "submitted": "submitted",
        "failed": "failed",
        "exception": "error",
        "buy_label": "Buy",
        "limit_buy_cmd": "Limit Buy",
        "market_buy_cmd": "Market Buy",
        "market_sell_cmd": "Market Sell",
        "dry_run_trade_log": "🧪 DRY_RUN {command} {symbol}: {quantity}{shares}",
        "dry_run_trade_log_with_price": "🧪 DRY_RUN {command} {symbol} (${price}): {quantity}{shares}",
        "post_sell_buying_power_unreleased": "ℹ️ Buying power did not update after the sell; skipped buys until the next run",
        "order_id_suffix": "(ID: {order_id})",
        "small_account_warning_note": "small account warning: portfolio equity {portfolio_equity} is below recommended {min_recommended_equity}; {reason}",
        "small_account_warning_reason_integer_shares_min_position_value_may_prevent_backtest_replication": "integer-share minimum position sizing may prevent backtest replication",
        "strategy_plugin_line": "🧩 Plugin: {plugin} | mode: {mode} | route: {route} | action: {action}",
        "strategy_plugin_name_crisis_response_shadow": "Crisis Response Shadow",
        "strategy_plugin_mode_shadow": "shadow",
        "strategy_plugin_mode_paper": "paper",
        "strategy_plugin_mode_advisory": "advisory",
        "strategy_plugin_mode_live": "live",
        "strategy_plugin_route_no_action": "no action",
        "strategy_plugin_route_true_crisis": "true crisis",
        "strategy_plugin_route_taco_fake_crisis": "TACO fake crisis",
        "strategy_plugin_route_unknown_route": "unknown route",
        "strategy_plugin_action_no_action": "no action",
        "strategy_plugin_action_watch_only": "watch only",
        "strategy_plugin_action_small_taco": "small TACO",
        "strategy_plugin_action_defend": "defend",
        "strategy_plugin_action_blocked": "blocked",
        "strategy_plugin_action_monitor": "monitor",
        "strategy_plugin_action_unknown_action": "unknown action",
        "strategy_name_tqqq_growth_income": "TQQQ Growth Income",
        "strategy_name_soxl_soxx_trend_income": "SOXL/SOXX Semiconductor Trend Income",
        "strategy_name_global_etf_rotation": "Global ETF Rotation",
        "strategy_name_russell_1000_multi_factor_defensive": "Russell 1000 Multi-Factor",
        "strategy_name_tech_communication_pullback_enhancement": "Tech/Communication Pullback Enhancement",
        "strategy_name_qqq_tech_enhancement": "Tech/Communication Pullback Enhancement",
        "strategy_name_mega_cap_leader_rotation_aggressive": "Mega Cap Leader Rotation Aggressive",
        "strategy_name_mega_cap_leader_rotation_dynamic_top20": "Mega Cap Leader Rotation Dynamic Top20",
        "strategy_name_mega_cap_leader_rotation_top50_balanced": "Mega Cap Leader Rotation Top50 Balanced",
        "strategy_name_dynamic_mega_leveraged_pullback": "Dynamic Mega Leveraged Pullback",
    },
}


def build_translator(lang):
    def translate(key, **kwargs):
        active_lang = lang if lang in I18N else "en"
        template = I18N[active_lang].get(key, key)
        return template.format(**kwargs) if kwargs else template

    return translate


def build_signal_text(translate_fn):
    def signal_text(icon_key):
        emoji = SIGNAL_ICONS.get(icon_key, "❓")
        name = translate_fn(f"signal_{icon_key}")
        return f"{emoji} {name}"

    return signal_text


def build_strategy_display_name(translate_fn):
    def strategy_display_name(profile: str, *, fallback_name: str | None = None) -> str:
        key = f"strategy_name_{str(profile or '').strip()}"
        translated = translate_fn(key)
        if translated != key:
            return translated
        fallback = str(fallback_name or "").strip()
        if fallback:
            return fallback
        return str(profile or "").strip()

    return strategy_display_name


def build_sender(token, chat_id, *, requests_module=requests):
    def send_tg_message(message):
        if not token or not chat_id:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            requests_module.post(url, json={"chat_id": chat_id, "text": message}, timeout=15)
        except Exception as exc:
            print(f"Telegram send failed: {exc}", flush=True)

    return send_tg_message
